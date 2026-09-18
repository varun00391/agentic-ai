from app.models import RunState


PER_ITEM_TOOLS = {
    "normalize_expense",
    "validate_expense",
    "categorize_expense",
    "check_duplicate",
    "evaluate_policy",
    "build_final_result",
    "request_human_review",
    "save_result",
}


def activate_item(state: RunState, index: int) -> None:
    if index < 0 or index >= len(state.extracted_items):
        raise ValueError("Item index is out of range")
    state.item_index = index
    state.extracted = state.extracted_items[index]
    state.normalized = None
    state.validation = None
    state.category = None
    state.duplicate = None
    state.policy_decision = None
    state.policy_reason = None
    state.final_status = None
    state.final_messages = []
    state.saved_result_id = None
    state.awaiting_human = False
    for tool in PER_ITEM_TOOLS:
        state.tool_attempts.pop(tool, None)


def remaining_item_count(state: RunState) -> int:
    if not state.extracted_items:
        return 0
    return max(0, len(state.extracted_items) - state.item_index - 1)


def advance_to_next_item(state: RunState) -> bool:
    next_index = state.item_index + 1
    if next_index >= len(state.extracted_items):
        return False
    activate_item(state, next_index)
    return True


def current_item_label(state: RunState) -> str:
    count = len(state.extracted_items) or 1
    index = min(state.item_index, count - 1) + 1
    merchant = None
    if state.extracted and state.extracted.merchant:
        merchant = state.extracted.merchant
    if merchant:
        return f"item {index} of {count} ({merchant})"
    return f"item {index} of {count}"
