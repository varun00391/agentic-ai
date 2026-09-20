from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import TraceEvent


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str
    organization_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str
    organizations: list["OrganizationSummary"]


class OrganizationSummary(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class JobSummary(BaseModel):
    job_id: str
    receipt_id: str
    filename: str
    status: str


class IngestResponse(BaseModel):
    batch_id: str
    jobs: list[JobSummary]


class JobProgress(BaseModel):
    step_count: int = 0
    current_tool: str | None = None
    current_reason: str | None = None
    current_arguments: dict[str, Any] = Field(default_factory=dict)
    merchant: str | None = None
    total: str | None = None
    currency: str | None = None
    category: str | None = None
    extraction_confidence: float | None = None
    extraction_source: str | None = None
    policy_decision: str | None = None
    final_status: str | None = None
    item_index: int = 0
    item_count: int = 0
    trace: list[TraceEvent] = Field(default_factory=list)


class JobDetail(BaseModel):
    job_id: str
    batch_id: str | None
    receipt_id: str
    organization_id: str
    filename: str
    status: str
    attempt_count: int
    error_message: str | None
    expense_id: str | None = None
    created_at: datetime
    updated_at: datetime
    progress: JobProgress = Field(default_factory=JobProgress)


class ExpenseDetail(BaseModel):
    expense_id: str
    organization_id: str
    receipt_id: str
    job_id: str
    filename: str | None = None
    merchant: str | None
    transaction_date: str | None
    total_minor_units: int | None
    currency: str | None
    category: str | None
    status: Literal["accepted", "needs_review", "duplicate", "failed", "rejected"]
    messages: list[str]
    duplicate_of_expense_id: str | None
    duplicate_match_type: str | None
    policy_decision: str | None
    extraction_confidence: float | None = None
    extraction_source: str | None = None
    step_count: int
    trace: list[TraceEvent]
    created_at: datetime


class ExpenseListResponse(BaseModel):
    items: list[ExpenseDetail]


class ReviewRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    merchant: str | None = None
    transaction_date: str | None = None
    total: str | None = None
    category: str | None = None
    reason: str | None = Field(default=None, max_length=300)


class MerchantMemoryItem(BaseModel):
    merchant: str
    category: str
    updated_at: datetime


class OrganizationPolicyResponse(BaseModel):
    extraction_min_confidence: float
    max_auto_accept_minor_units: int | None = None
    always_review_categories: list[str] = Field(default_factory=list)
    review_all: bool = False
    merchant_memories: list[MerchantMemoryItem] = Field(default_factory=list)


class OrganizationPolicyUpdate(BaseModel):
    extraction_min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_auto_accept_minor_units: int | None = Field(default=None, ge=0)
    always_review_categories: list[str] | None = None
    review_all: bool | None = None
    clear_max_auto_accept: bool = False


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    organizations: list[OrganizationSummary]
