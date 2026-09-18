from dataclasses import dataclass

from app.categorizer import categorize_expense
from app.config import Settings
from app.document import extract_document_text
from app.duplicates import expense_fingerprint
from app.evaluator import evaluate_final_status
from app.extractor import extract_expense_entries
from app.models import DuplicateResult, ExtractedExpense, Observation, RunState
from app.normalizer import normalize_expense
from app.repository import ExpenseRepository
from app.storage import ObjectStorage
from app.validator import validate_expense


@dataclass(frozen=True)
class RunContext:
    storage: ObjectStorage


class ToolRegistry:
    def __init__(
        self,
        settings: Settings,
        repository: ExpenseRepository,
        context: RunContext,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.context = context

    def execute(self, tool_name: str, state: RunState) -> Observation:
        handler = getattr(self, f"_run_{tool_name}", None)
        if handler is None:
            return Observation(
                success=False,
                summary=f"Unknown tool: {tool_name}",
                error_code="unknown_tool",
            )
        return handler(state)

    def _run_archive_receipt(self, state: RunState) -> Observation:
        if not self.context.storage.exists(state.object_key):
            return Observation(
                success=False,
                summary="Archived receipt object is missing",
                error_code="archive_missing",
                retryable=True,
            )
        state.archived = True
        return Observation(success=True, summary="Receipt archive confirmed")

    def _run_extract_document_text(self, state: RunState) -> Observation:
        content = self.context.storage.get(state.object_key)
        state.text = extract_document_text(content, state.content_type)
        return Observation(success=True, summary="Document text extracted")

    def _run_extract_expense_fields(self, state: RunState) -> Observation:
        items = extract_expense_entries(
            state.text or "", self.settings.primary_currency
        )
        if not items:
            items = [ExtractedExpense(currency=self.settings.primary_currency)]
        state.extracted_items = items
        state.extracted = items[0]
        count = len(items)
        return Observation(
            success=True,
            summary=(
                f"Extracted {count} expense{'s' if count != 1 else ''}"
                if count
                else "No expense fields extracted"
            ),
        )

    def _run_normalize_expense(self, state: RunState) -> Observation:
        if state.extracted is None:
            raise ValueError("Extracted fields are unavailable")
        state.normalized = normalize_expense(state.extracted)
        return Observation(success=True, summary="Expense fields normalized")

    def _run_validate_expense(self, state: RunState) -> Observation:
        if state.normalized is None:
            raise ValueError("Normalized expense is unavailable")
        state.validation = validate_expense(
            state.normalized,
            self.settings.supported_currencies,
            self.settings.max_total_minor_units,
        )
        summary = (
            "Expense validation passed"
            if state.validation.valid
            else f"Validation found {len(state.validation.messages)} issue(s)"
        )
        return Observation(success=True, summary=summary)

    def _run_categorize_expense(self, state: RunState) -> Observation:
        if state.normalized is None:
            raise ValueError("Normalized expense is unavailable")
        document_text = (
            state.normalized.merchant_raw or ""
            if len(state.extracted_items) > 1
            else (state.text or "")
        )
        state.category = categorize_expense(
            state.normalized.merchant_normalized, document_text
        )
        return Observation(
            success=True,
            summary=f"Expense categorized as {state.category}",
        )

    def _run_check_duplicate(self, state: RunState) -> Observation:
        fingerprint = expense_fingerprint(state.normalized)
        match = self.repository.find_duplicate(
            state.file_hash,
            fingerprint,
            receipt_id=state.receipt_id,
        )
        state.duplicate = DuplicateResult(
            is_duplicate=match is not None,
            duplicate_of_result_id=match[0] if match else None,
            match_type=match[1] if match else None,
        )
        return Observation(
            success=True,
            summary=(
                f"Duplicate matched result {match[0]}"
                if match
                else "No exact duplicate found"
            ),
        )

    def _run_evaluate_policy(self, state: RunState) -> Observation:
        if state.duplicate and state.duplicate.is_duplicate:
            state.policy_decision = "review_required"
            summary = "Policy flagged a duplicate for review routing"
        elif state.validation and not state.validation.valid:
            state.policy_decision = "review_required"
            summary = "Policy requires review because validation failed"
        else:
            state.policy_decision = "auto_accept"
            summary = "Policy allows auto-accept"
        return Observation(success=True, summary=summary)

    def _run_build_final_result(self, state: RunState) -> Observation:
        state.final_status, state.final_messages = evaluate_final_status(state)
        return Observation(
            success=True,
            summary=f"Final status is {state.final_status}",
        )

    def _run_save_result(self, state: RunState) -> Observation:
        saved_ids = [self.repository.save(state)]
        extra_items = list(state.extracted_items[1:])
        for extracted in extra_items:
            self._reset_item_state(state, extracted)
            self._run_normalize_expense(state)
            self._run_validate_expense(state)
            self._run_categorize_expense(state)
            self._run_check_duplicate(state)
            self._run_evaluate_policy(state)
            self._run_build_final_result(state)
            saved_ids.append(self.repository.save(state))
        state.saved_result_ids = saved_ids
        state.saved_result_id = saved_ids[0]
        count = len(saved_ids)
        self.repository.record_audit(
            "expense.saved",
            state.submitted_by_user_id,
            {
                "expense_ids": saved_ids,
                "status": state.final_status,
                "job_id": state.job_id,
            },
        )
        return Observation(
            success=True,
            summary=f"Saved {count} expense{'s' if count != 1 else ''}",
        )

    @staticmethod
    def _reset_item_state(state: RunState, extracted) -> None:
        state.extracted = extracted
        state.normalized = None
        state.validation = None
        state.category = None
        state.duplicate = None
        state.policy_decision = None
        state.final_status = None
        state.final_messages = []
        state.saved_result_id = None
