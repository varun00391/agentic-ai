from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ToolName = Literal[
    "archive_receipt",
    "extract_document_text",
    "extract_expense_fields",
    "normalize_expense",
    "validate_expense",
    "categorize_expense",
    "check_duplicate",
    "evaluate_policy",
    "build_final_result",
    "request_human_review",
    "save_result",
]

FinalStatus = Literal["accepted", "needs_review", "duplicate", "failed", "rejected"]
PolicyDecision = Literal["auto_accept", "review_required"]
RoleName = Literal["owner", "admin", "approver", "member", "auditor"]
ExtractionSource = Literal["llm", "regex", "human"]


class AgentAction(BaseModel):
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("arguments", mode="before")
    @classmethod
    def _coerce_arguments(cls, value: Any) -> dict[str, Any]:
        return value or {}


class Observation(BaseModel):
    success: bool
    summary: str
    error_code: str | None = None
    retryable: bool = False


class ExtractedExpense(BaseModel):
    merchant: str | None = None
    transaction_date: str | None = None
    total: str | None = None
    currency: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    extraction_source: ExtractionSource = "regex"


class NormalizedExpense(BaseModel):
    merchant_raw: str | None = None
    merchant_normalized: str | None = None
    transaction_date: date | None = None
    total_minor_units: int | None = None
    currency: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    messages: list[str] = Field(default_factory=list)


class DuplicateResult(BaseModel):
    is_duplicate: bool
    duplicate_of_result_id: str | None = None
    match_type: Literal["file_hash", "expense_fingerprint"] | None = None


class TraceEvent(BaseModel):
    step: int
    tool: str
    reason: str
    success: bool
    observation: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunState(BaseModel):
    run_id: str
    organization_id: str
    receipt_id: str
    job_id: str
    object_key: str
    filename: str
    content_type: str
    file_hash: str
    submitted_by_user_id: str
    text: str | None = None
    extracted: ExtractedExpense | None = None
    extracted_items: list[ExtractedExpense] = Field(default_factory=list)
    saved_result_ids: list[str] = Field(default_factory=list)
    normalized: NormalizedExpense | None = None
    validation: ValidationResult | None = None
    category: str | None = None
    duplicate: DuplicateResult | None = None
    policy_decision: PolicyDecision | None = None
    policy_reason: str | None = None
    final_status: FinalStatus | None = None
    final_messages: list[str] = Field(default_factory=list)
    saved_result_id: str | None = None
    awaiting_human: bool = False
    archived: bool = False
    ocr_attempted: bool = False
    vision_attempted: bool = False
    document_engine: str | None = None
    item_index: int = 0
    policy_min_confidence: float | None = None
    step_count: int = 0
    tool_attempts: dict[str, int] = Field(default_factory=dict)
    trace: list[TraceEvent] = Field(default_factory=list)
    current_tool: str | None = None
    current_reason: str | None = None
    current_arguments: dict[str, Any] = Field(default_factory=dict)
