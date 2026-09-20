from unittest.mock import MagicMock
from uuid import uuid4

import httpx
from openai import RateLimitError

from app.config import Settings
from app.models import ExtractedExpense, RunState
from app.planner import GroqPlanner, rate_limit_wait_seconds


def _state(**overrides) -> RunState:
    payload = {
        "run_id": str(uuid4()),
        "organization_id": "org",
        "receipt_id": "receipt",
        "job_id": "job",
        "object_key": "objects/receipt.jpg",
        "filename": "receipt.jpg",
        "content_type": "image/jpeg",
        "file_hash": "abc",
        "submitted_by_user_id": "user",
        "archived": False,
        "text": None,
    }
    payload.update(overrides)
    return RunState(**payload)


def _rate_limit_error(retry_after: str = "0") -> RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        429,
        headers={"retry-after": retry_after},
        request=request,
    )
    return RateLimitError("Rate limit reached", response=response, body=None)


def test_rate_limit_wait_respects_retry_after() -> None:
    wait = rate_limit_wait_seconds(_rate_limit_error("8"), attempt=0, max_wait=15)
    assert wait == 8


def test_groq_planner_skips_model_after_fields_are_extracted(settings: Settings) -> None:
    groq_settings = settings.model_copy(update={"groq_api_key": "test-key"})
    planner = GroqPlanner(groq_settings)
    planner.client.chat.completions.create = MagicMock()
    extracted = ExtractedExpense(
        merchant="SHARMA MEDICAL STORE",
        total="337",
        currency="INR",
        confidence=0.9,
        extraction_source="regex",
    )
    action = planner.choose_action(
        _state(
            archived=True,
            text="Paid to SHARMA MEDICAL STORE",
            extracted=extracted,
            extracted_items=[extracted],
        ),
        None,
    )
    assert action.tool == "normalize_expense"
    planner.client.chat.completions.create.assert_not_called()
    assert planner.degraded is False


def test_groq_planner_falls_back_after_rate_limit(
    monkeypatch, settings: Settings
) -> None:
    monkeypatch.setattr("app.planner.time.sleep", lambda _seconds: None)
    groq_settings = settings.model_copy(
        update={
            "groq_api_key": "test-key",
            "planner_rate_limit_retries": 1,
            "planner_rate_limit_max_wait_seconds": 0.01,
        }
    )
    planner = GroqPlanner(groq_settings)
    planner.client.chat.completions.create = MagicMock(side_effect=_rate_limit_error())
    action = planner.choose_action(_state(), None)
    assert action.tool == "archive_receipt"
    assert planner.degraded is True
    assert planner.client.chat.completions.create.call_count == 2
    second = planner.choose_action(_state(), None)
    assert second.tool == "archive_receipt"
    assert planner.client.chat.completions.create.call_count == 2
