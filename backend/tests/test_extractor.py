from app.config import Settings
from app.extractor import extract_expense_entries, extract_expense_fields
from app.llm_extract import LlmExtractionError
from app.models import ExtractedExpense
from app.normalizer import normalize_expense
from tests.conftest import RECEIPT_TEXT, STATEMENT_TEXT


def test_regex_receipt_fields() -> None:
    extracted = extract_expense_fields(RECEIPT_TEXT, "INR")
    assert extracted.merchant == "Fresh Mart"
    assert extracted.transaction_date == "01/09/2026"
    assert extracted.total == "123.45"
    assert extracted.extraction_source == "regex"
    assert extracted.confidence >= 0.7


def test_llm_extraction_is_used_when_groq_is_configured(monkeypatch) -> None:
    settings = Settings(groq_api_key="test-key", planner="rule_based")

    def fake_llm(text: str, primary_currency: str, _settings: Settings, hint=None):
        assert "Corner Cafe" in text
        return [
            ExtractedExpense(
                merchant="Corner Cafe",
                transaction_date="12 Mar 2026",
                total="499",
                currency=primary_currency,
                confidence=0.7,
                extraction_source="llm",
            )
        ]

    monkeypatch.setattr("app.extractor.extract_expenses_with_llm", fake_llm)
    items = extract_expense_entries(
        "Corner Cafe\n12 Mar 2026\nINR 499",
        "INR",
        settings,
    )
    assert len(items) == 1
    assert items[0].merchant == "Corner Cafe"
    assert items[0].extraction_source == "llm"
    assert items[0].confidence >= 0.85


def test_llm_failure_falls_back_to_regex(monkeypatch) -> None:
    settings = Settings(groq_api_key="test-key", planner="rule_based")

    def fail_llm(*_args, **_kwargs):
        raise LlmExtractionError("timeout")

    monkeypatch.setattr("app.extractor.extract_expenses_with_llm", fail_llm)
    items = extract_expense_entries(RECEIPT_TEXT, "INR", settings)
    assert items[0].merchant == "Fresh Mart"
    assert items[0].extraction_source == "regex"


def test_llm_that_collapses_a_statement_loses_to_regex(monkeypatch) -> None:
    settings = Settings(groq_api_key="test-key", planner="rule_based")

    def collapse_llm(*_args, **_kwargs):
        return [
            ExtractedExpense(
                merchant="SHARMA MEDICAL STORE",
                transaction_date="31 August",
                total="337",
                currency="INR",
                confidence=0.9,
                extraction_source="llm",
            )
        ]

    monkeypatch.setattr("app.extractor.extract_expenses_with_llm", collapse_llm)
    items = extract_expense_entries(STATEMENT_TEXT, "INR", settings)
    assert len(items) == 5
    assert items[0].extraction_source == "regex"
    assert [normalize_expense(item).merchant_raw for item in items] == [
        "SHARMA MEDICAL STORE",
        "SANJEEV KUMAR",
        "ZEEVA HEALTHCARE",
        "ZEEVA HEALTHCARE",
        "AHSAN TEA SHOP",
    ]


def test_missing_fields_cap_llm_confidence(monkeypatch) -> None:
    settings = Settings(groq_api_key="test-key", planner="rule_based")

    def weak_llm(*_args, **_kwargs):
        return [
            ExtractedExpense(
                merchant="Unknown Stall",
                transaction_date=None,
                total=None,
                currency="INR",
                confidence=0.95,
                extraction_source="llm",
            )
        ]

    monkeypatch.setattr("app.extractor.extract_expenses_with_llm", weak_llm)
    items = extract_expense_entries("blurry receipt", "INR", settings)
    assert items[0].confidence <= 0.45
