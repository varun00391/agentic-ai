from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db_models import (
    AuditEvent,
    Expense,
    Job,
    MerchantMemory,
    OrganizationPolicy,
    new_id,
    utcnow,
)
from app.duplicates import expense_fingerprint
from app.models import RunState
from app.policy import default_policy_values


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
            extraction_confidence=(
                state.extracted.confidence if state.extracted else None
            ),
            extraction_source=(
                state.extracted.extraction_source if state.extracted else None
            ),
            agent_step_count=state.step_count,
            agent_trace_json=[event.model_dump(mode="json") for event in state.trace],
        )
        self.session.add(expense)
        self.session.flush()
        return expense_id

    def apply_state(self, expense_id: str, state: RunState) -> None:
        expense = self.session.get(Expense, expense_id)
        if expense is None or expense.organization_id != self.organization_id:
            raise ValueError("Expense not found")
        normalized = state.normalized
        expense.expense_fingerprint = expense_fingerprint(normalized)
        expense.merchant_raw = normalized.merchant_raw if normalized else None
        expense.merchant_normalized = (
            normalized.merchant_normalized if normalized else None
        )
        expense.transaction_date = (
            normalized.transaction_date.isoformat()
            if normalized and normalized.transaction_date
            else None
        )
        expense.total_minor_units = (
            normalized.total_minor_units if normalized else None
        )
        expense.currency = normalized.currency if normalized else None
        expense.category = state.category
        expense.status = state.final_status or "failed"
        expense.validation_messages_json = list(state.final_messages)
        expense.duplicate_of_expense_id = (
            state.duplicate.duplicate_of_result_id if state.duplicate else None
        )
        expense.duplicate_match_type = (
            state.duplicate.match_type if state.duplicate else None
        )
        expense.policy_decision = state.policy_decision
        expense.extraction_confidence = (
            state.extracted.confidence if state.extracted else None
        )
        expense.extraction_source = (
            state.extracted.extraction_source if state.extracted else None
        )
        expense.agent_step_count = state.step_count
        expense.agent_trace_json = [
            event.model_dump(mode="json") for event in state.trace
        ]
        self.session.flush()

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
        job.heartbeat_at = datetime.now(timezone.utc)
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

    def get_or_create_policy(self, settings: Settings) -> OrganizationPolicy:
        row = self.session.get(OrganizationPolicy, self.organization_id)
        if row is not None:
            return row
        values = default_policy_values(settings)
        row = OrganizationPolicy(organization_id=self.organization_id, **values)
        self.session.add(row)
        self.session.flush()
        return row

    def update_policy(
        self,
        settings: Settings,
        extraction_min_confidence: float | None = None,
        max_auto_accept_minor_units: int | None = None,
        always_review_categories: list[str] | None = None,
        review_all: bool | None = None,
        clear_max_auto_accept: bool = False,
    ) -> OrganizationPolicy:
        row = self.get_or_create_policy(settings)
        if extraction_min_confidence is not None:
            row.extraction_min_confidence = extraction_min_confidence
        if clear_max_auto_accept:
            row.max_auto_accept_minor_units = None
        elif max_auto_accept_minor_units is not None:
            row.max_auto_accept_minor_units = max_auto_accept_minor_units
        if always_review_categories is not None:
            row.always_review_categories = always_review_categories
        if review_all is not None:
            row.review_all = review_all
        self.session.flush()
        return row

    def lookup_merchant(self, merchant_normalized: str | None) -> MerchantMemory | None:
        if not merchant_normalized:
            return None
        return self.session.scalar(
            select(MerchantMemory).where(
                MerchantMemory.organization_id == self.organization_id,
                MerchantMemory.merchant_normalized == merchant_normalized,
            )
        )

    def remember_merchant(
        self,
        merchant_normalized: str | None,
        category: str | None,
        merchant_display: str | None = None,
    ) -> None:
        if not merchant_normalized or not category:
            return
        existing = self.lookup_merchant(merchant_normalized)
        if existing is not None:
            existing.category = category
            if merchant_display:
                existing.merchant_display = merchant_display
            existing.updated_at = utcnow()
        else:
            self.session.add(
                MerchantMemory(
                    organization_id=self.organization_id,
                    merchant_normalized=merchant_normalized,
                    merchant_display=merchant_display,
                    category=category,
                )
            )
        self.session.flush()

    def list_merchant_memories(self) -> list[MerchantMemory]:
        return list(
            self.session.scalars(
                select(MerchantMemory)
                .where(MerchantMemory.organization_id == self.organization_id)
                .order_by(MerchantMemory.updated_at.desc())
            ).all()
        )
