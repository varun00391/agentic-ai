from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorizer import CATEGORIES
from app.config import Settings
from app.db_models import Expense, Job, Receipt
from app.models import ExtractedExpense, RunState, TraceEvent
from app.repository import ExpenseRepository
from app.storage import ObjectStorage
from app.tools import RunContext, ToolRegistry


class ReviewError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def apply_review(
    session: Session,
    settings: Settings,
    expense: Expense,
    actor_user_id: str,
    decision: str,
    merchant: str | None = None,
    transaction_date: str | None = None,
    total: str | None = None,
    category: str | None = None,
    reason: str | None = None,
) -> Expense:
    if expense.status != "needs_review":
        raise ReviewError(409, "Only expenses that need review can be decided")
    if category and category not in CATEGORIES:
        raise ReviewError(400, f"Unsupported category: {category}")

    repository = ExpenseRepository(session, expense.organization_id)
    job = session.get(Job, expense.job_id)
    if decision == "reject":
        return _reject(repository, expense, job, actor_user_id, reason)

    tools = ToolRegistry(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    )
    state = _load_state(session, expense, job)
    _apply_human_fields(
        state,
        merchant=merchant,
        transaction_date=transaction_date,
        total=total,
        category=category,
        edited=decision == "edit",
    )
    _append_human_trace(
        state,
        "Approved with edits" if decision == "edit" else "Approved as-is",
    )
    tools._run_normalize_expense(state)
    tools._run_validate_expense(state)
    if state.validation is None or not state.validation.valid:
        messages = (
            state.validation.messages
            if state.validation
            else ["The edited fields are incomplete"]
        )
        raise ReviewError(400, "; ".join(messages))
    if category:
        state.category = category
    else:
        tools._run_categorize_expense(state)
    tools._run_check_duplicate(state)
    if state.duplicate and state.duplicate.is_duplicate:
        state.policy_decision = "review_required"
        state.policy_reason = "Policy flagged a duplicate for review routing"
    else:
        state.policy_decision = "auto_accept"
        state.policy_reason = None
    tools._run_build_final_result(state)
    state.awaiting_human = False
    if state.final_status == "accepted" and state.normalized is not None:
        repository.remember_merchant(
            state.normalized.merchant_normalized,
            state.category,
            state.normalized.merchant_raw,
        )
    repository.apply_state(expense.id, state)
    repository.save_checkpoint(expense.job_id, state)
    if job is not None and job.status == "waiting_for_review":
        remaining = session.scalar(
            select(Expense.id).where(
                Expense.job_id == job.id,
                Expense.status == "needs_review",
                Expense.id != expense.id,
            )
        )
        if remaining is None:
            job.status = "succeeded"
            job.error_message = None
    repository.record_audit(
        "expense.reviewed",
        actor_user_id,
        {
            "expense_id": expense.id,
            "decision": decision,
            "status": state.final_status,
        },
    )
    session.flush()
    session.refresh(expense)
    return expense


def _reject(
    repository: ExpenseRepository,
    expense: Expense,
    job: Job | None,
    actor_user_id: str,
    reason: str | None,
) -> Expense:
    message = reason.strip() if reason and reason.strip() else "Rejected by a reviewer"
    expense.status = "rejected"
    expense.validation_messages_json = [message]
    expense.policy_decision = "review_required"
    trace = list(expense.agent_trace_json or [])
    next_step = (expense.agent_step_count or 0) + 1
    trace.append(
        TraceEvent(
            step=next_step,
            tool="human_review",
            reason=message,
            success=True,
            observation="Receipt rejected",
        ).model_dump(mode="json")
    )
    expense.agent_step_count = next_step
    expense.agent_trace_json = trace
    if job is not None and job.status == "waiting_for_review":
        remaining = repository.session.scalar(
            select(Expense.id).where(
                Expense.job_id == job.id,
                Expense.status == "needs_review",
                Expense.id != expense.id,
            )
        )
        if remaining is None:
            job.status = "succeeded"
            job.error_message = None
    repository.record_audit(
        "expense.rejected",
        actor_user_id,
        {"expense_id": expense.id, "reason": message},
    )
    return expense


def _load_state(session: Session, expense: Expense, job: Job | None) -> RunState:
    extracted = ExtractedExpense(
        merchant=expense.merchant_raw,
        transaction_date=expense.transaction_date,
        total=(
            f"{expense.total_minor_units / 100:.2f}"
            if expense.total_minor_units is not None
            else None
        ),
        currency=expense.currency,
        confidence=expense.extraction_confidence or 0.5,
        extraction_source=expense.extraction_source or "regex",  # type: ignore[arg-type]
    )
    if job and job.checkpoint_json:
        state = RunState.model_validate(job.checkpoint_json)
    else:
        receipt = session.get(Receipt, expense.receipt_id)
        state = RunState(
            run_id=str(uuid4()),
            organization_id=expense.organization_id,
            receipt_id=expense.receipt_id,
            job_id=expense.job_id,
            object_key=receipt.object_key if receipt else "",
            filename=receipt.filename if receipt else "",
            content_type=receipt.content_type if receipt else "image/png",
            file_hash=expense.file_hash,
            submitted_by_user_id=expense.submitted_by_user_id,
            step_count=expense.agent_step_count,
        )
    state.extracted = extracted
    state.extracted_items = [extracted]
    state.item_index = 0
    state.saved_result_id = expense.id
    state.saved_result_ids = [expense.id]
    state.category = expense.category
    state.awaiting_human = True
    return state


def _apply_human_fields(
    state: RunState,
    merchant: str | None,
    transaction_date: str | None,
    total: str | None,
    category: str | None,
    edited: bool,
) -> None:
    current = state.extracted or ExtractedExpense()
    updates = {
        "confidence": 1.0,
        "extraction_source": "human" if edited else current.extraction_source,
    }
    if merchant is not None:
        updates["merchant"] = merchant.strip() or None
    if transaction_date is not None:
        updates["transaction_date"] = transaction_date.strip() or None
    if total is not None:
        updates["total"] = total.strip() or None
    state.extracted = current.model_copy(update=updates)
    if state.extracted_items:
        state.extracted_items[0] = state.extracted
    else:
        state.extracted_items = [state.extracted]
    if category:
        state.category = category
    state.normalized = None
    state.validation = None
    state.duplicate = None
    state.policy_decision = None
    state.policy_reason = None
    state.final_status = None
    state.final_messages = []
    state.awaiting_human = False


def _append_human_trace(state: RunState, summary: str) -> None:
    state.step_count += 1
    state.trace.append(
        TraceEvent(
            step=state.step_count,
            tool="human_review",
            reason=summary,
            success=True,
            observation=summary,
        )
    )
