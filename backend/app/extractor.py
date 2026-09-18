import re

from app.models import ExtractedExpense


DATE_PATTERNS = [
    r"\b(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b",
    r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b",
    r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4})\b",
    r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b",
    r"\b(today|yesterday|\d+\s+hours?\s+ago|\d+\s+days?\s+ago)\b",
]

AMOUNT_PATTERN = (
    r"(?:₹|rs\.?|inr|\$|usd|€|eur|£|gbp)\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
)
BARE_AMOUNT_PATTERN = (
    r"^\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.\d{1,2})?|[0-9]{2,}(?:\.\d{1,2})?)\s*$"
)

TOTAL_PATTERNS = [
    r"(?:grand\s+total|amount\s+paid|total\s+amount|net\s+amount|total)\s*[:\-]?\s*"
    + AMOUNT_PATTERN,
    AMOUNT_PATTERN,
]

LABEL_PATTERN = re.compile(
    r"^(receipt|invoice|tax invoice|date|time|phone|gstin|total|"
    r"paid to|received from|debited from|credited to|debit|credit|"
    r"amount|status|success|failed)$",
    re.IGNORECASE,
)

ENTRY_SPLIT = re.compile(
    r"(?i)(?=(?:^|\n)\s*(?:paid to|received from)\b)"
)


def extract_expense_fields(text: str, primary_currency: str) -> ExtractedExpense:
    entries = extract_expense_entries(text, primary_currency)
    if entries:
        return entries[0]
    return ExtractedExpense(currency=primary_currency)


def extract_expense_entries(text: str, primary_currency: str) -> list[ExtractedExpense]:
    currency = _extract_currency(text) or primary_currency
    statement_entries = _extract_statement_entries(text, currency)
    if len(statement_entries) >= 2:
        return statement_entries
    if statement_entries:
        return statement_entries
    amount_entries = _extract_amount_anchored_entries(text, currency)
    if len(amount_entries) >= 2:
        return amount_entries
    fallback = ExtractedExpense(
        merchant=_extract_merchant(text),
        transaction_date=_first_match(text, DATE_PATTERNS),
        total=_first_match(text, TOTAL_PATTERNS),
        currency=currency,
    )
    if fallback.merchant or fallback.total:
        return [fallback]
    return []


def _extract_statement_entries(text: str, currency: str) -> list[ExtractedExpense]:
    chunks = [
        chunk.strip()
        for chunk in ENTRY_SPLIT.split(text)
        if re.search(r"(?i)\b(?:paid to|received from)\b", chunk)
    ]
    entries: list[ExtractedExpense] = []
    for chunk in chunks:
        merchant = _extract_merchant(chunk)
        total = _amount_from_text(chunk)
        if merchant is None and total is None:
            continue
        entries.append(
            ExtractedExpense(
                merchant=merchant,
                transaction_date=_first_match(chunk, DATE_PATTERNS),
                total=total,
                currency=currency,
            )
        )
    return entries


def _extract_amount_anchored_entries(text: str, currency: str) -> list[ExtractedExpense]:
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
    entries: list[ExtractedExpense] = []
    for index, line in enumerate(lines):
        total = _amount_from_text(line)
        if total is None:
            continue
        window = lines[max(0, index - 4) : index + 3]
        merchant = next(
            (name for item in window if (name := _merchant_from_line(item))),
            None,
        )
        transaction_date = next(
            (match for item in window if (match := _first_match(item, DATE_PATTERNS))),
            None,
        )
        if merchant is None:
            continue
        entries.append(
            ExtractedExpense(
                merchant=merchant,
                transaction_date=transaction_date,
                total=total,
                currency=currency,
            )
        )
    return _unique_entries(entries)


def _extract_merchant(text: str) -> str | None:
    for line in text.splitlines():
        merchant = _merchant_from_line(_clean_line(line))
        if merchant:
            return merchant
    return None


def _looks_like_merchant(value: str | None) -> bool:
    return _merchant_from_line(value) is not None


def _merchant_from_line(value: str | None) -> str | None:
    if not value:
        return None
    candidate = _clean_line(value)
    if not candidate or LABEL_PATTERN.search(candidate):
        return None
    candidate = re.sub(AMOUNT_PATTERN, "", candidate, flags=re.IGNORECASE).strip(" :-")
    if not candidate or LABEL_PATTERN.search(candidate):
        return None
    date_value = _first_match(candidate, DATE_PATTERNS)
    if date_value and date_value.casefold() == candidate.casefold():
        return None
    if not (2 <= len(candidate) <= 100):
        return None
    if not any(character.isalpha() for character in candidate):
        return None
    return candidate


def _clean_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line).strip(" :-")
    return re.sub(
        r"(?i)^(paid to|received from|debited from|credited to)\s*",
        "",
        cleaned,
    ).strip(" :-")


def _amount_from_text(text: str) -> str | None:
    marked = _first_match(text, [AMOUNT_PATTERN])
    if marked:
        return marked
    for line in text.splitlines():
        match = re.match(BARE_AMOUNT_PATTERN, _clean_line(line), re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_currency(text: str) -> str | None:
    lowered = text.lower()
    currency_markers = [
        (("₹", "inr", "rs.", "rs "), "INR"),
        (("$", "usd"), "USD"),
        (("€", "eur"), "EUR"),
        (("£", "gbp"), "GBP"),
    ]
    for markers, code in currency_markers:
        if any(marker in lowered for marker in markers):
            return code
    return None


def _unique_entries(entries: list[ExtractedExpense]) -> list[ExtractedExpense]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    unique: list[ExtractedExpense] = []
    for entry in entries:
        key = (entry.merchant, entry.transaction_date, entry.total)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique
