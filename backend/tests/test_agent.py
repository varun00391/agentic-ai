from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent import ExpenseAgent
from app.config import Settings
from app.db_models import Job, Organization, Receipt, User, new_id
from app.duplicates import hash_file
from app.models import AgentAction, RunState
from app.repository import ExpenseRepository
from app.security import hash_password
from app.storage import ObjectStorage
from app.tools import RunContext
from tests.conftest import RECEIPT_TEXT, STATEMENT_TEXT


def _seed_run(
    session: Session,
    settings: Settings,
    organization: Organization | None = None,
    user: User | None = None,
    content: bytes = b"receipt-one",
) -> tuple[RunState, ExpenseRepository]:
    if organization is None:
        organization = Organization(name="Acme", slug=f"acme-{new_id()[:8]}")
        session.add(organization)
    if user is None:
        user = User(
            email=f"{new_id()[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="Owner",
        )
        session.add(user)
    session.flush()
    receipt = Receipt(
        organization_id=organization.id,
        uploaded_by_user_id=user.id,
        filename="receipt.png",
        content_type="image/png",
        file_hash="abc",
        object_key="pending",
        source="upload",
        malware_scan_status="clean",
        size_bytes=len(content),
    )
    session.add(receipt)
    session.flush()
    storage = ObjectStorage(settings.object_storage_path)
    receipt.object_key = storage.put(organization.id, receipt.id, receipt.filename, content)
    receipt.file_hash = hash_file(content)
    job = Job(
        organization_id=organization.id,
        receipt_id=receipt.id,
        created_by_user_id=user.id,
        status="running",
    )
    session.add(job)
    session.commit()
    state = RunState(
        run_id=str(uuid4()),
        organization_id=organization.id,
        receipt_id=receipt.id,
        job_id=job.id,
        object_key=receipt.object_key,
        filename=receipt.filename,
        content_type=receipt.content_type,
        file_hash=receipt.file_hash,
        submitted_by_user_id=user.id,
    )
    return state, ExpenseRepository(session, organization.id)


def test_statement_screenshot_extracts_each_vendor() -> None:
    from app.extractor import extract_expense_entries
    from app.normalizer import normalize_expense

    entries = extract_expense_entries(STATEMENT_TEXT, "INR")
    normalized = [normalize_expense(entry) for entry in entries]

    assert [item.merchant_raw for item in normalized] == [
        "SHARMA MEDICAL STORE",
        "SANJEEV KUMAR",
        "ZEEVA HEALTHCARE",
        "ZEEVA HEALTHCARE",
        "AHSAN TEA SHOP",
    ]
    assert [item.total_minor_units for item in normalized] == [
        33700,
        14400,
        380000,
        60000,
        20800,
    ]
    assert {item.transaction_date.isoformat() for item in normalized} == {"2026-08-31"}


def test_ocr_statement_without_rupee_signs() -> None:
    from app.extractor import extract_expense_entries
    from app.normalizer import normalize_expense

    text = """
Paid to
7
ZEEVA HEALTHCARE
3,800
31 August
Debited from
Paid to
7
ZEEVA HEALTHCARE
600
31 August
Debited from
"""
    entries = extract_expense_entries(text, "INR")
    normalized = [normalize_expense(entry) for entry in entries]
    assert [item.merchant_raw for item in normalized] == [
        "ZEEVA HEALTHCARE",
        "ZEEVA HEALTHCARE",
    ]
    assert [item.total_minor_units for item in normalized] == [380000, 60000]


def test_agent_saves_each_statement_vendor(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: STATEMENT_TEXT,
    )
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    ).process(state)

    from sqlalchemy import select

    from app.db_models import Expense

    expenses = db_session.scalars(
        select(Expense).where(Expense.job_id == state.job_id).order_by(Expense.created_at)
    ).all()
    assert result.final_status in {"accepted", "needs_review"}
    assert len(result.saved_result_ids) == 5
    assert [row.merchant_raw for row in expenses] == [
        "SHARMA MEDICAL STORE",
        "SANJEEV KUMAR",
        "ZEEVA HEALTHCARE",
        "ZEEVA HEALTHCARE",
        "AHSAN TEA SHOP",
    ]
    assert [row.total_minor_units for row in expenses] == [
        33700,
        14400,
        380000,
        60000,
        20800,
    ]


def test_extraction_normalization_and_validation() -> None:
    from app.extractor import extract_expense_fields
    from app.normalizer import normalize_expense
    from app.validator import validate_expense

    extracted = extract_expense_fields(RECEIPT_TEXT, "INR")
    normalized = normalize_expense(extracted)
    validation = validate_expense(normalized, ["INR"], 100_000_000)

    assert normalized.merchant_raw == "Fresh Mart"
    assert normalized.transaction_date.isoformat() == "2026-09-01"
    assert normalized.total_minor_units == 12_345
    assert validation.valid is True


def test_agent_completes_full_flow(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    ).process(state)

    assert result.final_status == "accepted"
    assert result.category == "groceries"
    assert result.normalized is not None
    assert result.normalized.total_minor_units == 12_345
    assert result.saved_result_id is not None
    assert [event.tool for event in result.trace] == [
        "archive_receipt",
        "extract_document_text",
        "extract_expense_fields",
        "normalize_expense",
        "validate_expense",
        "categorize_expense",
        "check_duplicate",
        "evaluate_policy",
        "build_final_result",
        "save_result",
    ]


def test_agent_detects_exact_duplicate(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    first_state, repository = _seed_run(db_session, settings)
    storage = ObjectStorage(settings.object_storage_path)
    agent = ExpenseAgent(settings, repository, RunContext(storage=storage))
    first = agent.process(first_state)

    org = db_session.get(Organization, first_state.organization_id)
    user = db_session.get(User, first_state.submitted_by_user_id)
    second_state, repository = _seed_run(
        db_session, settings, organization=org, user=user, content=b"receipt-one"
    )
    second = ExpenseAgent(settings, repository, RunContext(storage=storage)).process(
        second_state
    )

    assert first.final_status == "accepted"
    assert second.final_status == "duplicate"
    assert second.duplicate is not None
    assert second.duplicate.match_type == "expense_fingerprint"
    assert second.duplicate.duplicate_of_result_id == first.saved_result_id


def test_missing_total_needs_review(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "Corner Store\nDate: 01/09/2026",
    )
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    ).process(state)

    assert result.final_status == "needs_review"
    assert "Total amount is missing or invalid" in result.final_messages


class RepeatingPlanner:
    def choose_action(self, state, latest_observation):
        return AgentAction(
            tool="extract_document_text",
            reason="Repeat extraction to exercise the retry guard",
        )


def test_agent_stops_repeated_tool_calls(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
        planner=RepeatingPlanner(),
    ).process(state)

    assert result.final_status == "failed"
    assert result.step_count == 3
    assert result.final_messages == ["Retry limit reached for extract_document_text"]
