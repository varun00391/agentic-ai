import hashlib
import re

from app.models import NormalizedExpense


def hash_file(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def expense_fingerprint(expense: NormalizedExpense | None) -> str | None:
    if (
        expense is None
        or not expense.merchant_normalized
        or expense.transaction_date is None
        or expense.total_minor_units is None
        or not expense.currency
    ):
        return None
    merchant = re.sub(r"[^a-z0-9]", "", expense.merchant_normalized)
    value = "|".join(
        [
            merchant,
            expense.transaction_date.isoformat(),
            str(expense.total_minor_units),
            expense.currency,
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
