from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent import ExpenseAgent
from app.config import Settings
from app.db_models import Job, Organization, Receipt, User, new_id
from app.duplicates import hash_file
from app.models import AgentAction, ExtractedExpense, RunState
from app.repository import ExpenseRepository
from app.security import hash_password
from app.storage import ObjectStorage
from app.planner import RuleBasedPlanner
from app.tools import RunContext, ToolRegistry
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
    tools = [event.tool for event in result.trace]
    assert tools.count("normalize_expense") == 5
    assert tools.count("evaluate_policy") == 5
    assert tools.count("save_result") == 5


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
    assert result.current_tool is None
    assert result.current_reason is None


def test_agent_checkpoints_in_progress_tool(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    seen: list[tuple[str | None, str | None]] = []
    original = ToolRegistry.execute

    def wrapped(self, tool, state, arguments):
        seen.append((state.current_tool, state.current_reason))
        return original(self, tool, state, arguments)

    monkeypatch.setattr(ToolRegistry, "execute", wrapped)
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    ).process(state)

    assert result.final_status == "accepted"
    assert seen
    assert all(tool for tool, _reason in seen)
    assert seen[0][0] == "archive_receipt"
    assert seen[0][1]


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
    assert result.awaiting_human is True
    assert result.saved_result_id is not None
    assert "Total amount is missing or invalid" in result.final_messages
    assert result.trace[-1].tool == "request_human_review"


def test_low_extraction_confidence_needs_review(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    monkeypatch.setattr(
        "app.tools.extract_expense_entries",
        lambda text, primary_currency, _settings=None, hint=None: [
            ExtractedExpense(
                merchant="Fresh Mart",
                transaction_date="01/09/2026",
                total="123.45",
                currency="INR",
                confidence=0.4,
                extraction_source="llm",
            )
        ],
    )
    state, repository = _seed_run(db_session, settings)
    result = ExpenseAgent(
        settings,
        repository,
        RunContext(storage=ObjectStorage(settings.object_storage_path)),
    ).process(state)

    assert result.final_status == "needs_review"
    assert result.awaiting_human is True
    assert result.extracted is not None
    assert result.extracted.confidence == 0.4
    assert any("confidence" in message for message in result.final_messages)
    assert result.trace[-1].tool == "request_human_review"


class RepeatingPlanner:
    def choose_action(self, state, latest_observation):
        return AgentAction(
            tool="extract_document_text",
            reason="Repeat extraction to exercise the retry guard",
        )


class FailOnSecondItemPlanner:
    def __init__(self, settings: Settings) -> None:
        self.inner = RuleBasedPlanner(settings)

    def choose_action(self, state, latest_observation):
        if (
            state.item_index == 1
            and state.duplicate is not None
            and state.policy_decision is None
        ):
            raise ValueError("simulated RateLimitError")
        return self.inner.choose_action(state, latest_observation)


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


def test_planner_failure_still_finishes_remaining_statement_items(
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
        planner=FailOnSecondItemPlanner(settings),
    ).process(state)

    from sqlalchemy import select

    from app.db_models import Expense

    expenses = db_session.scalars(
        select(Expense).where(Expense.job_id == state.job_id).order_by(Expense.created_at)
    ).all()
    assert [row.merchant_raw for row in expenses] == [
        "SHARMA MEDICAL STORE",
        "SANJEEV KUMAR",
        "ZEEVA HEALTHCARE",
        "ZEEVA HEALTHCARE",
        "AHSAN TEA SHOP",
    ]
    assert [row.status for row in expenses] == [
        "accepted",
        "failed",
        "accepted",
        "accepted",
        "accepted",
    ]
    assert "Planner retry limit reached" in (expenses[1].validation_messages_json or [])
    assert len(result.saved_result_ids) == 5


def test_weak_ocr_retries_with_vision(
    monkeypatch, settings: Settings, db_session: Session
) -> None:
    vision_settings = settings.model_copy(update={"groq_api_key": "test-key"})
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "blur",
    )
    monkeypatch.setattr(
        "app.tools.extract_document_text_with_vision",
        lambda content, content_type, _settings: RECEIPT_TEXT,
    )
    state, repository = _seed_run(db_session, vision_settings)
    result = ExpenseAgent(
        vision_settings,
        repository,
        RunContext(storage=ObjectStorage(vision_settings.object_storage_path)),
    ).process(state)

    assert result.ocr_attempted is True
    assert result.vision_attempted is True
    assert result.document_engine == "vision"
    assert result.final_status == "accepted"
    assert result.normalized is not None
    assert result.normalized.total_minor_units == 12_345
    document_steps = [
        event.observation for event in result.trace if event.tool == "extract_document_text"
    ]
    assert any("via ocr" in step for step in document_steps)
    assert any("via vision" in step for step in document_steps)
