from collections.abc import Callable

from app.config import Settings
from app.evaluator import goal_completed
from app.guardrails import validate_action
from app.models import Observation, RunState, TraceEvent
from app.planner import Planner, create_planner
from app.repository import ExpenseRepository
from app.tools import RunContext, ToolRegistry


class ExpenseAgent:
    def __init__(
        self,
        settings: Settings,
        repository: ExpenseRepository,
        context: RunContext,
        planner: Planner | None = None,
        on_checkpoint: Callable[[RunState], None] | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.context = context
        self.planner = planner or create_planner(settings)
        self.on_checkpoint = on_checkpoint

    def process(self, state: RunState) -> RunState:
        tools = ToolRegistry(self.settings, self.repository, self.context)
        latest_observation: Observation | None = None
        planner_failures = 0
        if goal_completed(state):
            return state

        while state.step_count < self.settings.max_agent_steps:
            self._set_working(state, None, "Deciding the next step")
            self._checkpoint(state)
            try:
                action = self.planner.choose_action(state, latest_observation)
            except Exception as exc:
                planner_failures += 1
                state.step_count += 1
                latest_observation = Observation(
                    success=False,
                    summary=f"Planner response was invalid: {type(exc).__name__}",
                    error_code="invalid_planner_response",
                    retryable=planner_failures < self.settings.max_tool_retries,
                )
                self._clear_working(state)
                self._append_trace(
                    state, "planner", "Select the next approved tool", latest_observation
                )
                self._checkpoint(state)
                if planner_failures >= self.settings.max_tool_retries:
                    self._force_failure(state, "Planner retry limit reached")
                    break
                continue

            state.step_count += 1
            guard_error = validate_action(
                action, state, self.settings.max_tool_retries
            )
            if guard_error:
                latest_observation = Observation(
                    success=False,
                    summary=guard_error,
                    error_code="action_rejected",
                    retryable=False,
                )
                self._clear_working(state)
                self._append_trace(state, action.tool, action.reason, latest_observation)
                self._checkpoint(state)
                if "Retry limit reached" in guard_error:
                    self._force_failure(state, guard_error)
                    break
                continue

            state.tool_attempts[action.tool] = (
                state.tool_attempts.get(action.tool, 0) + 1
            )
            self._set_working(state, action.tool, action.reason, action.arguments)
            self._checkpoint(state)
            try:
                latest_observation = tools.execute(
                    action.tool, state, action.arguments
                )
            except Exception as exc:
                exhausted = (
                    state.tool_attempts[action.tool] >= self.settings.max_tool_retries
                )
                latest_observation = Observation(
                    success=False,
                    summary=f"{action.tool} failed: {type(exc).__name__}",
                    error_code="tool_execution_failed",
                    retryable=not exhausted,
                )

            self._clear_working(state)
            self._append_trace(state, action.tool, action.reason, latest_observation)
            self._checkpoint(state)

            if (
                action.tool in {"save_result", "request_human_review"}
                and latest_observation.success
                and state.saved_result_ids
            ):
                self.repository.update_trace(state.saved_result_ids[-1], state)

            if not latest_observation.success and not latest_observation.retryable:
                self._force_failure(state, latest_observation.summary)
                break
            if goal_completed(state):
                break
        else:
            self._force_failure(state, "Maximum agent steps reached")

        if state.awaiting_human:
            self._clear_working(state)
            self._checkpoint(state)
            return state
        if state.final_status is None:
            self._force_failure(state, "Agent stopped without a final result")
        self._clear_working(state)
        self._checkpoint(state)
        return state

    def _checkpoint(self, state: RunState) -> None:
        self.repository.save_checkpoint(state.job_id, state)
        if self.on_checkpoint is not None:
            self.on_checkpoint(state)

    @staticmethod
    def _set_working(
        state: RunState,
        tool: str | None,
        reason: str | None,
        arguments: dict | None = None,
    ) -> None:
        state.current_tool = tool
        state.current_reason = reason
        state.current_arguments = dict(arguments or {})

    @staticmethod
    def _clear_working(state: RunState) -> None:
        state.current_tool = None
        state.current_reason = None
        state.current_arguments = {}

    @staticmethod
    def _append_trace(
        state: RunState,
        tool: str,
        reason: str,
        observation: Observation,
    ) -> None:
        state.trace.append(
            TraceEvent(
                step=state.step_count,
                tool=tool,
                reason=reason,
                success=observation.success,
                observation=observation.summary,
            )
        )

    def _force_failure(self, state: RunState, reason: str) -> None:
        if state.awaiting_human or state.saved_result_id is not None:
            return
        self._clear_working(state)
        state.final_status = "failed"
        state.final_messages = [reason]
        try:
            state.saved_result_id = self.repository.save(state)
        except Exception:
            state.saved_result_id = None
        self._checkpoint(state)
