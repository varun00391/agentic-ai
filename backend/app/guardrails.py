from app.models import AgentAction, RunState

ALLOWED_ARGUMENT_KEYS = {
    "extract_document_text": {"engine"},
    "extract_expense_fields": {"hint"},
}

ALLOWED_ENGINES = {"ocr", "vision"}
MAX_HINT_LENGTH = 200


def validate_action(
    action: AgentAction,
    state: RunState,
    max_tool_retries: int,
) -> str | None:
    argument_error = _validate_arguments(action)
    if argument_error:
        return argument_error

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
        "request_human_review": (
            state.final_status == "needs_review" and not state.awaiting_human
        ),
        "save_result": (
            state.final_status is not None and state.final_status != "needs_review"
        ),
    }
    if action.tool in prerequisites and not prerequisites[action.tool]:
        return f"Prerequisites are not satisfied for {action.tool}"
    return None


def _validate_arguments(action: AgentAction) -> str | None:
    allowed = ALLOWED_ARGUMENT_KEYS.get(action.tool)
    if not action.arguments:
        return None
    if allowed is None:
        return f"{action.tool} does not accept model-provided arguments"
    unknown = sorted(set(action.arguments) - allowed)
    if unknown:
        return f"{action.tool} does not accept arguments {unknown}"
    if action.tool == "extract_document_text":
        engine = action.arguments.get("engine", "ocr")
        if engine not in ALLOWED_ENGINES:
            return "engine must be ocr or vision"
    if action.tool == "extract_expense_fields":
        hint = action.arguments.get("hint")
        if hint is not None and not isinstance(hint, str):
            return "hint must be a string"
        if isinstance(hint, str) and len(hint) > MAX_HINT_LENGTH:
            return f"hint must be at most {MAX_HINT_LENGTH} characters"
    return None
