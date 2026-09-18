from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_models import AuditEvent, Expense, Job, new_id
from app.duplicates import expense_fingerprint
from app.models import RunState


class ExpenseRepository:
    def __init__(self, session: Session, organization_id: str) -> None:
        self.session = session
        self.organization_id = organization_id

    def find_duplicate(
        self,
        file_hash: str,
        fingerprint: str | None,
        receipt_id: str | None = None,
    ) -> tuple[str, str] | None:
        if fingerprint:
            fingerprint_query = select(Expense).where(
                Expense.organization_id == self.organization_id,
                Expense.expense_fingerprint == fingerprint,
                Expense.status.in_(("accepted", "needs_review")),
            )
            if receipt_id:
                fingerprint_query = fingerprint_query.where(
                    Expense.receipt_id != receipt_id
                )
            row = self.session.scalar(fingerprint_query)
            if row is not None:
                return row.id, "expense_fingerprint"
            return None
        file_query = select(Expense).where(
            Expense.organization_id == self.organization_id,
            Expense.file_hash == file_hash,
            Expense.status.in_(("accepted", "needs_review")),
        )
        if receipt_id:
            file_query = file_query.where(Expense.receipt_id != receipt_id)
        row = self.session.scalar(file_query)
        if row is not None:
            return row.id, "file_hash"
        return None

    def save(self, state: RunState) -> str:
        normalized = state.normalized
        expense_id = new_id()
        expense = Expense(
            id=expense_id,
            organization_id=self.organization_id,
            receipt_id=state.receipt_id,
            job_id=state.job_id,
            submitted_by_user_id=state.submitted_by_user_id,
            file_hash=state.file_hash,
            expense_fingerprint=expense_fingerprint(normalized),
            merchant_raw=normalized.merchant_raw if normalized else None,
            merchant_normalized=normalized.merchant_normalized if normalized else None,
            transaction_date=(
                normalized.transaction_date.isoformat()
                if normalized and normalized.transaction_date
                else None
            ),
            total_minor_units=normalized.total_minor_units if normalized else None,
            currency=normalized.currency if normalized else None,
            category=state.category,
            status=state.final_status or "failed",
            validation_messages_json=list(state.final_messages),
            duplicate_of_expense_id=(
                state.duplicate.duplicate_of_result_id if state.duplicate else None
            ),
            duplicate_match_type=(
                state.duplicate.match_type if state.duplicate else None
            ),
            policy_decision=state.policy_decision,
            agent_step_count=state.step_count,
            agent_trace_json=[event.model_dump(mode="json") for event in state.trace],
        )
        self.session.add(expense)
        self.session.flush()
        return expense_id

    def update_trace(self, expense_id: str, state: RunState) -> None:
        expense = self.session.get(Expense, expense_id)
        if expense is None or expense.organization_id != self.organization_id:
            return
        expense.agent_step_count = state.step_count
        expense.agent_trace_json = [
            event.model_dump(mode="json") for event in state.trace
        ]

    def save_checkpoint(self, job_id: str, state: RunState) -> None:
        job = self.session.get(Job, job_id)
        if job is None or job.organization_id != self.organization_id:
            raise ValueError("Job not found for checkpoint")
        payload = state.model_dump(mode="json")
        job.checkpoint_json = payload
        job.heartbeat_at = state.trace[-1].created_at if state.trace else job.heartbeat_at
        self.session.flush()

    def record_audit(
        self,
        event_type: str,
        actor_user_id: str | None,
        payload: dict,
    ) -> None:
        self.session.add(
            AuditEvent(
                organization_id=self.organization_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                payload=payload,
            )
        )
