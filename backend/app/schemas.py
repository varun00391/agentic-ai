from datetime import datetime, timezone
from typing import Literal

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
    status: Literal["accepted", "needs_review", "duplicate", "failed"]
    messages: list[str]
    duplicate_of_expense_id: str | None
    duplicate_match_type: str | None
    policy_decision: str | None
    step_count: int
    trace: list[TraceEvent]
    created_at: datetime


class ExpenseListResponse(BaseModel):
    items: list[ExpenseDetail]


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    organizations: list[OrganizationSummary]
