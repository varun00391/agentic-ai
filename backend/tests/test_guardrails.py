from app.guardrails import validate_action
from app.models import AgentAction, ExtractedExpense, RunState


def _state(**kwargs) -> RunState:
    payload = {
        "run_id": "run",
        "organization_id": "org",
        "receipt_id": "receipt",
        "job_id": "job",
        "object_key": "object",
        "filename": "receipt.png",
        "content_type": "image/png",
        "file_hash": "hash",
        "submitted_by_user_id": "user",
    }
    payload.update(kwargs)
    return RunState.model_validate(payload)


def test_allows_ocr_and_vision_engine() -> None:
    state = _state(archived=True)
    for engine in ("ocr", "vision"):
        error = validate_action(
            AgentAction(
                tool="extract_document_text",
                arguments={"engine": engine},
                reason="Read the document",
            ),
            state,
            2,
        )
        assert error is None


def test_allows_extraction_hint() -> None:
    state = _state(text="Fresh Mart\nTotal 10")
    error = validate_action(
        AgentAction(
            tool="extract_expense_fields",
            arguments={"hint": "Prefer grand total"},
            reason="Retry extraction",
        ),
        state,
        2,
    )
    assert error is None


def test_rejects_unknown_argument() -> None:
    state = _state(extracted=ExtractedExpense(merchant="A", total="1"))
    error = validate_action(
        AgentAction(
            tool="normalize_expense",
            arguments={"foo": "bar"},
            reason="Normalize",
        ),
        state,
        2,
    )
    assert error is not None
    assert "does not accept" in error


def test_rejects_invalid_engine() -> None:
    state = _state(archived=True)
    error = validate_action(
        AgentAction(
            tool="extract_document_text",
            arguments={"engine": "magic"},
            reason="Bad engine",
        ),
        state,
        2,
    )
    assert error == "engine must be ocr or vision"
