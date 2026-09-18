from app.models import AgentAction, RunState


def validate_action(
    action: AgentAction,
    state: RunState,
    max_tool_retries: int,
) -> str | None:
    if action.arguments:
        return f"{action.tool} does not accept model-provided arguments"

    attempts = state.tool_attempts.get(action.tool, 0)
    if attempts >= max_tool_retries:
        return f"Retry limit reached for {action.tool}"

    prerequisites = {
        "extract_expense_fields": state.text is not None,
        "normalize_expense": state.extracted is not None,
        "validate_expense": state.normalized is not None,
        "categorize_expense": state.normalized is not None and state.text is not None,
        "check_duplicate": state.normalized is not None,
        "evaluate_policy": (
            state.validation is not None
            and state.category is not None
            and state.duplicate is not None
        ),
        "build_final_result": state.policy_decision is not None,
        "save_result": state.final_status is not None,
    }
    if action.tool in prerequisites and not prerequisites[action.tool]:
        return f"Prerequisites are not satisfied for {action.tool}"
    return None
