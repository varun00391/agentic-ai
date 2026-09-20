from datetime import date, timedelta

from app.models import NormalizedExpense, ValidationResult


def validate_expense(
    expense: NormalizedExpense,
    supported_currencies: list[str],
    max_total_minor_units: int,
) -> ValidationResult:
    messages: list[str] = []

    if not expense.merchant_normalized:
        messages.append("Merchant is missing")
    if expense.transaction_date is None:
        messages.append("Transaction date is missing or invalid")
    elif expense.transaction_date > date.today() + timedelta(days=1):
        messages.append("Transaction date cannot be in the future")
    if expense.total_minor_units is None:
        messages.append("Total amount is missing or invalid")
    elif expense.total_minor_units <= 0:
        messages.append("Total amount must be positive")
    elif expense.total_minor_units > max_total_minor_units:
        messages.append("Total amount exceeds the configured limit")
    if not expense.currency:
        messages.append("Currency is missing")
    elif expense.currency not in supported_currencies:
        messages.append(f"Unsupported currency: {expense.currency}")

    return ValidationResult(valid=not messages, messages=messages)
