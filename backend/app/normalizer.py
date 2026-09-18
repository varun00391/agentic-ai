import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.models import ExtractedExpense, NormalizedExpense


DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d %b %y",
    "%d %B %y",
)
YEARLESS_DATE_FORMATS = ("%d %B", "%d %b")


def normalize_expense(extracted: ExtractedExpense) -> NormalizedExpense:
    merchant_raw = extracted.merchant.strip() if extracted.merchant else None
    merchant_normalized = (
        re.sub(r"\s+", " ", merchant_raw).casefold() if merchant_raw else None
    )
    return NormalizedExpense(
        merchant_raw=merchant_raw,
        merchant_normalized=merchant_normalized,
        transaction_date=_normalize_date(extracted.transaction_date),
        total_minor_units=_normalize_amount(extracted.total),
        currency=extracted.currency.upper().strip() if extracted.currency else None,
    )


def _normalize_date(value: str | None):
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.strip())
    lowered = cleaned.casefold()
    if lowered == "today" or re.fullmatch(r"\d+\s+hours?\s+ago", lowered):
        return date.today()
    if lowered == "yesterday":
        return date.today() - timedelta(days=1)
    days_ago = re.fullmatch(r"(\d+)\s+days?\s+ago", lowered)
    if days_ago:
        return date.today() - timedelta(days=int(days_ago.group(1)))
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    for date_format in YEARLESS_DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
        today = date.today()
        guessed = parsed.replace(year=today.year)
        if guessed > today + timedelta(days=1):
            return guessed.replace(year=today.year - 1)
        return guessed
    return None


def _normalize_amount(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
