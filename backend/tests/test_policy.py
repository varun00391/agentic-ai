from app.jobs import process_available_jobs
from app.repository import ExpenseRepository
from tests.conftest import PNG_BYTES, RECEIPT_TEXT, auth_headers, signup


def test_policy_api_roundtrip(client) -> None:
    body = signup(client, "policy-owner@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)

    fetched = client.get("/api/v2/organization/policy", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["extraction_min_confidence"] == 0.7
    assert fetched.json()["review_all"] is False
    assert fetched.json()["merchant_memories"] == []

    updated = client.put(
        "/api/v2/organization/policy",
        headers=headers,
        json={
            "extraction_min_confidence": 0.9,
            "max_auto_accept_minor_units": 5000,
            "always_review_categories": ["travel"],
            "review_all": False,
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["extraction_min_confidence"] == 0.9
    assert payload["max_auto_accept_minor_units"] == 5000
    assert payload["always_review_categories"] == ["travel"]


def test_org_policy_sends_large_amount_to_review(
    client, settings, monkeypatch, db_session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    body = signup(client, "cap@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)
    repository = ExpenseRepository(db_session, org_id)
    repository.update_policy(settings, max_auto_accept_minor_units=10000)
    db_session.commit()

    ingest = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    job_id = ingest.json()["jobs"][0]["job_id"]
    process_available_jobs(db_session, settings)

    job = client.get(f"/api/v2/jobs/{job_id}", headers=headers)
    assert job.json()["status"] == "waiting_for_review"
    expense = client.get(
        f"/api/v2/expenses/{job.json()['expense_id']}", headers=headers
    )
    assert expense.json()["status"] == "needs_review"
    assert "auto-accept limit" in " ".join(expense.json()["messages"])


def test_merchant_memory_from_review_is_reused(
    client, settings, monkeypatch, db_session
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "Corner Store\nDate: 01/09/2026",
    )
    body = signup(client, "memory@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)
    first = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("one.png", PNG_BYTES, "image/png")},
    )
    process_available_jobs(db_session, settings)
    first_job = client.get(
        f"/api/v2/jobs/{first.json()['jobs'][0]['job_id']}", headers=headers
    )
    expense_id = first_job.json()["expense_id"]
    edited = client.post(
        f"/api/v2/expenses/{expense_id}/review",
        headers=headers,
        json={
            "decision": "edit",
            "merchant": "Blue Kiosk",
            "transaction_date": "01/09/2026",
            "total": "20.00",
            "category": "shopping",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["category"] == "shopping"

    policy = client.get("/api/v2/organization/policy", headers=headers)
    memories = policy.json()["merchant_memories"]
    assert memories
    assert memories[0]["category"] == "shopping"

    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "Blue Kiosk\nDate: 02/09/2026\nGrand Total: INR 20.00",
    )
    second = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("two.png", PNG_BYTES, "image/png")},
    )
    process_available_jobs(db_session, settings)
    second_job = client.get(
        f"/api/v2/jobs/{second.json()['jobs'][0]['job_id']}", headers=headers
    )
    reused = client.get(
        f"/api/v2/expenses/{second_job.json()['expense_id']}", headers=headers
    )
    assert reused.json()["status"] == "accepted"
    assert reused.json()["category"] == "shopping"


def test_always_review_category(client, settings, monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    body = signup(client, "always@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)
    ExpenseRepository(db_session, org_id).update_policy(
        settings, always_review_categories=["groceries"]
    )
    db_session.commit()

    ingest = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    process_available_jobs(db_session, settings)
    job = client.get(
        f"/api/v2/jobs/{ingest.json()['jobs'][0]['job_id']}", headers=headers
    )
    expense = client.get(
        f"/api/v2/expenses/{job.json()['expense_id']}", headers=headers
    )
    assert expense.json()["status"] == "needs_review"
    assert expense.json()["category"] == "groceries"
