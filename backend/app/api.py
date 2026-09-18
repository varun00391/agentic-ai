import mimetypes
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import bootstrap_if_needed, get_session, init_engine
from app.db_models import (
    AuditEvent,
    Expense,
    Job,
    JobBatch,
    Membership,
    Organization,
    Receipt,
    User,
)
from app.deps import (
    AuthContext,
    WRITE_ROLES,
    get_auth_context,
    get_current_user,
    require_roles,
)
from app.duplicates import hash_file
from app.document import SUPPORTED_CONTENT_TYPES
from app.scan import scan_receipt
from app.schemas import (
    ExpenseDetail,
    ExpenseListResponse,
    IngestResponse,
    JobDetail,
    JobSummary,
    LoginRequest,
    MeResponse,
    OrganizationSummary,
    SignupRequest,
    TokenResponse,
)
from app.security import (
    create_access_token,
    hash_password,
    slugify,
    verify_password,
)
from app.storage import ObjectStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_engine(settings)
    bootstrap_if_needed(settings)
    yield


app = FastAPI(
    title="Expense Capture Platform",
    version="0.2.0",
    description="Multi-tenant production API for asynchronous receipt processing.",
    lifespan=lifespan,
)

_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origin_list or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _organizations_for(session: Session, user_id: str) -> list[OrganizationSummary]:
    rows = session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    ).all()
    return [
        OrganizationSummary(id=org.id, name=org.name, slug=org.slug, role=role)
        for org, role in rows
    ]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v2/auth/signup", response_model=TokenResponse)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    email = payload.email.strip().casefold()
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    session.add(user)
    session.flush()
    base_slug = slugify(payload.organization_name)
    slug = base_slug
    if session.scalar(select(Organization).where(Organization.slug == slug)):
        slug = f"{base_slug}-{user.id[:8]}"
    organization = Organization(name=payload.organization_name.strip(), slug=slug)
    session.add(organization)
    session.flush()
    session.add(
        Membership(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )
    )
    session.flush()
    token = create_access_token(
        user.id, user.email, settings.jwt_secret, settings.jwt_expire_minutes
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organizations=_organizations_for(session, user.id),
    )


@app.post("/api/v2/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    email = payload.email.strip().casefold()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(
        user.id, user.email, settings.jwt_secret, settings.jwt_expire_minutes
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organizations=_organizations_for(session, user.id),
    )


@app.get("/api/v2/organizations", response_model=list[OrganizationSummary])
def list_organizations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[OrganizationSummary]:
    return _organizations_for(session, user.id)


@app.get("/api/v2/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organizations=_organizations_for(session, user.id),
    )


@app.post("/api/v2/receipts", response_model=IngestResponse)
async def ingest_receipts(
    files: list[UploadFile] = File(...),
    auth: AuthContext = Depends(require_roles(*WRITE_ROLES)),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=400,
            detail=f"A batch can contain at most {settings.max_batch_files} files",
        )

    if idempotency_key:
        existing = session.scalar(
            select(JobBatch).where(
                JobBatch.organization_id == auth.organization.id,
                JobBatch.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return _batch_response(session, existing)

    storage = ObjectStorage(settings.object_storage_path)
    batch = JobBatch(
        organization_id=auth.organization.id,
        created_by_user_id=auth.user.id,
        total_jobs=len(files),
        idempotency_key=idempotency_key,
    )
    session.add(batch)
    session.flush()

    jobs: list[Job] = []
    for upload in files:
        content, filename, content_type = await _read_receipt(upload, settings)
        try:
            scan_status = scan_receipt(content, content_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        receipt = Receipt(
            organization_id=auth.organization.id,
            uploaded_by_user_id=auth.user.id,
            filename=filename,
            content_type=content_type,
            file_hash=hash_file(content),
            object_key="pending",
            source="upload",
            malware_scan_status=scan_status,
            size_bytes=len(content),
        )
        session.add(receipt)
        session.flush()
        receipt.object_key = storage.put(
            auth.organization.id, receipt.id, filename, content
        )
        job = Job(
            organization_id=auth.organization.id,
            receipt_id=receipt.id,
            batch_id=batch.id,
            created_by_user_id=auth.user.id,
            status="queued",
        )
        session.add(job)
        jobs.append(job)

    session.flush()
    session.add(
        AuditEvent(
            organization_id=auth.organization.id,
            actor_user_id=auth.user.id,
            event_type="receipt.ingested",
            payload={"batch_id": batch.id, "job_count": len(jobs)},
        )
    )
    return IngestResponse(
        batch_id=batch.id,
        jobs=[
            JobSummary(
                job_id=job.id,
                receipt_id=job.receipt_id,
                filename=next(
                    receipt.filename
                    for receipt in session.scalars(
                        select(Receipt).where(Receipt.id == job.receipt_id)
                    )
                ),
                status=job.status,
            )
            for job in jobs
        ],
    )


@app.get("/api/v2/jobs/{job_id}", response_model=JobDetail)
def get_job(
    job_id: str,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
) -> JobDetail:
    job = session.get(Job, job_id)
    if job is None or job.organization_id != auth.organization.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if auth.role == "member" and job.created_by_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    receipt = session.get(Receipt, job.receipt_id)
    expense = session.scalar(
        select(Expense).where(
            Expense.job_id == job.id,
            Expense.organization_id == auth.organization.id,
        )
    )
    return JobDetail(
        job_id=job.id,
        batch_id=job.batch_id,
        receipt_id=job.receipt_id,
        organization_id=job.organization_id,
        filename=receipt.filename if receipt else "",
        status=job.status,
        attempt_count=job.attempt_count,
        error_message=job.error_message,
        expense_id=expense.id if expense else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@app.get("/api/v2/batches/{batch_id}", response_model=IngestResponse)
def get_batch(
    batch_id: str,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
) -> IngestResponse:
    batch = session.get(JobBatch, batch_id)
    if batch is None or batch.organization_id != auth.organization.id:
        raise HTTPException(status_code=404, detail="Batch not found")
    if auth.role == "member" and batch.created_by_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="Batch not found")
    return _batch_response(session, batch)


@app.get("/api/v2/expenses", response_model=ExpenseListResponse)
def list_expenses(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
) -> ExpenseListResponse:
    query = select(Expense, Receipt.filename).join(
        Receipt, Receipt.id == Expense.receipt_id
    ).where(Expense.organization_id == auth.organization.id)
    if auth.role == "member":
        query = query.where(Expense.submitted_by_user_id == auth.user.id)
    rows = session.execute(query.order_by(Expense.created_at.desc())).all()
    return ExpenseListResponse(
        items=[_expense_detail(expense, filename) for expense, filename in rows]
    )


@app.get("/api/v2/expenses/{expense_id}", response_model=ExpenseDetail)
def get_expense(
    expense_id: str,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
) -> ExpenseDetail:
    expense = session.get(Expense, expense_id)
    if expense is None or expense.organization_id != auth.organization.id:
        raise HTTPException(status_code=404, detail="Expense not found")
    if auth.role == "member" and expense.submitted_by_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="Expense not found")
    receipt = session.get(Receipt, expense.receipt_id)
    return _expense_detail(expense, receipt.filename if receipt else None)


def _expense_detail(expense: Expense, filename: str | None) -> ExpenseDetail:
    return ExpenseDetail(
        expense_id=expense.id,
        organization_id=expense.organization_id,
        receipt_id=expense.receipt_id,
        job_id=expense.job_id,
        filename=filename,
        merchant=expense.merchant_raw,
        transaction_date=expense.transaction_date,
        total_minor_units=expense.total_minor_units,
        currency=expense.currency,
        category=expense.category,
        status=expense.status,  # type: ignore[arg-type]
        messages=list(expense.validation_messages_json or []),
        duplicate_of_expense_id=expense.duplicate_of_expense_id,
        duplicate_match_type=expense.duplicate_match_type,
        policy_decision=expense.policy_decision,
        step_count=expense.agent_step_count,
        trace=expense.agent_trace_json or [],
        created_at=expense.created_at,
    )


def _batch_response(session: Session, batch: JobBatch) -> IngestResponse:
    jobs = session.scalars(
        select(Job).where(Job.batch_id == batch.id).order_by(Job.created_at)
    ).all()
    items: list[JobSummary] = []
    for job in jobs:
        receipt = session.get(Receipt, job.receipt_id)
        items.append(
            JobSummary(
                job_id=job.id,
                receipt_id=job.receipt_id,
                filename=receipt.filename if receipt else "",
                status=job.status,
            )
        )
    return IngestResponse(batch_id=batch.id, jobs=items)


async def _read_receipt(
    file: UploadFile, settings: Settings
) -> tuple[bytes, str, str]:
    filename = file.filename or "receipt"
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or ""
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG, and PDF receipts are supported",
        )
    content = await file.read(settings.max_file_size_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_file_size_mb} MB limit",
        )
    return content, filename, content_type
