from app.config import Settings
from app.db_models import OrganizationPolicy
from app.models import PolicyDecision, RunState


def default_policy_values(settings: Settings) -> dict:
    return {
        "extraction_min_confidence": settings.extraction_min_confidence,
        "max_auto_accept_minor_units": None,
        "always_review_categories": [],
        "review_all": False,
    }


def min_confidence(state: RunState, settings: Settings) -> float:
    if state.policy_min_confidence is not None:
        return state.policy_min_confidence
    return settings.extraction_min_confidence


def decide_policy(
    state: RunState,
    policy: OrganizationPolicy,
) -> tuple[PolicyDecision, str | None]:
    if state.duplicate and state.duplicate.is_duplicate:
        return "review_required", "Policy flagged a duplicate for review routing"
    if state.validation and not state.validation.valid:
        return "review_required", "Policy requires review because validation failed"
    if policy.review_all:
        return "review_required", "Organization policy requires review for every expense"
    extracted = state.extracted
    if extracted is not None and extracted.confidence < policy.extraction_min_confidence:
        return (
            "review_required",
            "Policy requires review because extraction confidence "
            f"{extracted.confidence:.0%} is below "
            f"{policy.extraction_min_confidence:.0%}",
        )
    amount = state.normalized.total_minor_units if state.normalized else None
    cap = policy.max_auto_accept_minor_units
    if cap is not None and amount is not None and amount > cap:
        return (
            "review_required",
            "Policy requires review because the amount exceeds the auto-accept limit",
        )
    always_review = {
        str(item) for item in (policy.always_review_categories or []) if item
    }
    if state.category and state.category in always_review:
        return (
            "review_required",
            f"Organization policy always reviews {state.category.replace('_', ' ')}",
        )
    return "auto_accept", None
