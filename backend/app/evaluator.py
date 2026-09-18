from app.models import FinalStatus, RunState


def evaluate_final_status(state: RunState) -> tuple[FinalStatus, list[str]]:
    if state.duplicate and state.duplicate.is_duplicate:
        return "duplicate", [
            f"Matches existing result {state.duplicate.duplicate_of_result_id}"
        ]
    if state.policy_decision == "review_required":
        messages = list(state.validation.messages) if state.validation else []
        if not messages:
            messages = ["Policy requires human review"]
        return "needs_review", messages
    if state.validation and not state.validation.valid:
        return "needs_review", list(state.validation.messages)
    if state.validation and state.validation.valid:
        return "accepted", ["All required checks passed"]
    return "failed", ["The agent could not produce a complete result"]


def goal_completed(state: RunState) -> bool:
    return state.saved_result_id is not None and state.final_status is not None
