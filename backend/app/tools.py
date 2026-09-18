from dataclasses import dataclass

from app.categorizer import categorize_expense
from app.config import Settings
from app.document import extract_document_text, extract_document_text_with_vision
from app.duplicates import expense_fingerprint
from app.evaluator import evaluate_final_status
from app.extractor import extract_expense_entries
from app.items import advance_to_next_item, current_item_label
from app.models import DuplicateResult, ExtractedExpense, Observation, RunState
from app.normalizer import normalize_expense
from app.policy import decide_policy
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

    def execute(
        self,
        tool_name: str,
        state: RunState,
        arguments: dict | None = None,
    ) -> Observation:
        handler = getattr(self, f"_run_{tool_name}", None)
        if handler is None:
            return Observation(
                success=False,
                summary=f"Unknown tool: {tool_name}",
                error_code="unknown_tool",
            )
        payload = arguments or {}
        if tool_name == "extract_document_text":
            return self._run_extract_document_text(state, payload)
        if tool_name == "extract_expense_fields":
            return self._run_extract_expense_fields(state, payload)
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

    def _run_extract_document_text(
        self, state: RunState, arguments: dict | None = None
    ) -> Observation:
        engine = (arguments or {}).get("engine") or "ocr"
        content = self.context.storage.get(state.object_key)
        try:
            if engine == "vision":
                state.vision_attempted = True
                text = extract_document_text_with_vision(
                    content, state.content_type, self.settings
                )
            else:
                state.ocr_attempted = True
                text = extract_document_text(content, state.content_type)
        except Exception as exc:
            return Observation(
                success=False,
                summary=f"{engine} read failed: {exc}",
                error_code="document_read_failed",
                retryable=True,
            )
        _replace_document_text(state, text, engine)
        return Observation(
            success=True,
            summary=f"Document text extracted via {engine} ({len(text)} chars)",
        )

    def _run_extract_expense_fields(
        self, state: RunState, arguments: dict | None = None
    ) -> Observation:
        hint = (arguments or {}).get("hint")
        items = extract_expense_entries(
            state.text or "",
            self.settings.primary_currency,
            self.settings,
            hint=hint if isinstance(hint, str) else None,
        )
        if not items:
            items = [
                ExtractedExpense(
                    currency=self.settings.primary_currency,
                    confidence=0.1,
                    extraction_source="regex",
                )
            ]
        state.extracted_items = items
        state.extracted = items[0]
        state.item_index = 0
        count = len(items)
        lowest = min(item.confidence for item in items)
        source = items[0].extraction_source
        mixed = any(item.extraction_source != source for item in items)
        source_label = "mixed" if mixed else source
        return Observation(
            success=True,
            summary=(
                f"Extracted {count} expense{'s' if count != 1 else ''} via "
                f"{source_label} (confidence {lowest:.0%})"
                + (" with hint" if hint else "")
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
        remembered = self.repository.lookup_merchant(
            state.normalized.merchant_normalized
        )
        remembered_category = remembered.category if remembered else None
        state.category = categorize_expense(
            state.normalized.merchant_normalized,
            document_text,
            remembered_category,
        )
        source = "merchant memory" if remembered_category else "keywords"
        return Observation(
            success=True,
            summary=f"Expense categorized as {state.category} via {source}",
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
        policy = self.repository.get_or_create_policy(self.settings)
        state.policy_min_confidence = policy.extraction_min_confidence
        decision, reason = decide_policy(state, policy)
        state.policy_decision = decision
        state.policy_reason = reason
        summary = reason or "Policy allows auto-accept"
        return Observation(success=True, summary=summary)

    def _run_build_final_result(self, state: RunState) -> Observation:
        state.final_status, state.final_messages = evaluate_final_status(state)
        return Observation(
            success=True,
            summary=f"Final status is {state.final_status}",
        )

    def _run_request_human_review(self, state: RunState) -> Observation:
        if state.final_status != "needs_review":
            return Observation(
                success=False,
                summary="Human review is only for needs_review results",
                error_code="review_not_required",
            )
        expense_id = self.repository.save(state)
        state.saved_result_id = expense_id
        if expense_id not in state.saved_result_ids:
            state.saved_result_ids.append(expense_id)
        label = current_item_label(state)
        reason = state.policy_reason or (
            state.final_messages[0] if state.final_messages else "A human should review this receipt"
        )
        self.repository.record_audit(
            "expense.review_requested",
            state.submitted_by_user_id,
            {"expense_id": expense_id, "job_id": state.job_id, "reason": reason},
        )
        if advance_to_next_item(state):
            return Observation(
                success=True,
                summary=f"Paused {label} for review; continuing with the next item",
            )
        state.awaiting_human = True
        return Observation(
            success=True,
            summary=f"Paused for human review: {reason}",
        )

    def _run_save_result(self, state: RunState) -> Observation:
        expense_id = self.repository.save(state)
        state.saved_result_id = expense_id
        if expense_id not in state.saved_result_ids:
            state.saved_result_ids.append(expense_id)
        label = current_item_label(state)
        remaining = len(state.extracted_items) - len(state.saved_result_ids)
        self.repository.record_audit(
            "expense.saved",
            state.submitted_by_user_id,
            {
                "expense_id": expense_id,
                "expense_ids": list(state.saved_result_ids),
                "status": state.final_status,
                "job_id": state.job_id,
            },
        )
        if advance_to_next_item(state):
            return Observation(
                success=True,
                summary=f"Saved {label}; {remaining} remaining",
            )
        count = len(state.saved_result_ids) or 1
        return Observation(
            success=True,
            summary=f"Saved {count} expense{'s' if count != 1 else ''}",
        )


def _replace_document_text(state: RunState, text: str, engine: str) -> None:
    state.text = text
    state.document_engine = engine
    state.extracted = None
    state.extracted_items = []
    state.normalized = None
    state.validation = None
    state.category = None
    state.duplicate = None
    state.policy_decision = None
    state.policy_reason = None
    state.final_status = None
    state.final_messages = []
    state.item_index = 0
    state.saved_result_id = None
