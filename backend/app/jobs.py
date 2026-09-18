from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import ExpenseAgent
from app.config import Settings
from app.db_models import Job, Receipt
from app.models import RunState
from app.repository import ExpenseRepository
from app.storage import ObjectStorage
from app.tools import RunContext


def reclaim_stale_jobs(session: Session, settings: Settings) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.stale_job_seconds)
    jobs = session.scalars(
        select(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)
    ).all()
    for job in jobs:
        job.status = "queued"
        job.claimed_at = None
    session.flush()
    return len(jobs)


def claim_job(session: Session) -> Job | None:
    stmt = select(Job).where(Job.status == "queued").order_by(Job.created_at)
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = session.scalars(stmt.limit(1)).first()
    if job is None:
        return None
    job.status = "running"
    job.claimed_at = datetime.now(timezone.utc)
    job.heartbeat_at = job.claimed_at
    job.attempt_count += 1
    session.flush()
    return job


def process_job(session: Session, settings: Settings, job: Job) -> Job:
    receipt = session.get(Receipt, job.receipt_id)
    if receipt is None or receipt.organization_id != job.organization_id:
        job.status = "failed"
        job.error_message = "Receipt is missing"
        return job

    storage = ObjectStorage(settings.object_storage_path)
    repository = ExpenseRepository(session, job.organization_id)
    if job.checkpoint_json:
        state = RunState.model_validate(job.checkpoint_json)
    else:
        state = RunState(
            run_id=str(uuid4()),
            organization_id=job.organization_id,
            receipt_id=receipt.id,
            job_id=job.id,
            object_key=receipt.object_key,
            filename=receipt.filename,
            content_type=receipt.content_type,
            file_hash=receipt.file_hash,
            submitted_by_user_id=job.created_by_user_id,
        )

    def on_checkpoint(_state: RunState) -> None:
        job.heartbeat_at = datetime.now(timezone.utc)
        session.commit()

    agent = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=storage),
        on_checkpoint=on_checkpoint,
    )
    try:
        state = agent.process(state)
        job.status = "succeeded"
        job.error_message = None
        if not settings.retain_ocr_text and job.checkpoint_json:
            checkpoint = dict(job.checkpoint_json)
            checkpoint["text"] = None
            job.checkpoint_json = checkpoint
        repository.record_audit(
            "job.completed",
            job.created_by_user_id,
            {"job_id": job.id, "status": state.final_status},
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        job = session.get(Job, job.id) or job
        if job.attempt_count >= settings.max_job_attempts:
            job.status = "dead_letter"
        else:
            job.status = "queued"
        job.error_message = type(exc).__name__
        session.commit()
    return job


def process_available_jobs(session: Session, settings: Settings, limit: int = 10) -> int:
    reclaim_stale_jobs(session, settings)
    processed = 0
    for _ in range(limit):
        job = claim_job(session)
        if job is None:
            break
        process_job(session, settings, job)
        processed += 1
    return processed
