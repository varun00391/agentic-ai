from app.jobs import process_available_jobs
from tests.conftest import PNG_BYTES, RECEIPT_TEXT, auth_headers, signup


def test_signup_and_login(client) -> None:
    body = signup(client, "owner@example.com", organization="Northwind")
    assert body["access_token"]
    assert body["organizations"][0]["role"] == "owner"

    login = client.post(
        "/api/v2/auth/login",
        json={"email": "owner@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == body["user_id"]
    assert login.json()["email"] == "owner@example.com"

    me = client.get(
        "/api/v2/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["display_name"] == "Owner"


def test_ingest_is_async_and_worker_completes_job(
    client, settings, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: RECEIPT_TEXT,
    )
    body = signup(client, "async@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)

    ingest = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert ingest.status_code == 200, ingest.text
    payload = ingest.json()
    assert payload["jobs"][0]["status"] == "queued"
    job_id = payload["jobs"][0]["job_id"]

    queued = client.get(f"/api/v2/jobs/{job_id}", headers=headers)
    assert queued.json()["status"] == "queued"

    from app.db import get_session_factory

    session = get_session_factory()()
    try:
        processed = process_available_jobs(session, settings)
    finally:
        session.close()
    assert processed == 1

    done = client.get(f"/api/v2/jobs/{job_id}", headers=headers)
    assert done.status_code == 200
    assert done.json()["status"] == "succeeded"
    expense_id = done.json()["expense_id"]
    assert expense_id

    expense = client.get(f"/api/v2/expenses/{expense_id}", headers=headers)
    assert expense.status_code == 200
    assert expense.json()["status"] == "accepted"
    assert expense.json()["merchant"] == "Fresh Mart"
    assert len(done.json()["progress"]["trace"]) >= 8
    assert done.json()["progress"]["merchant"] == "Fresh Mart"


def test_rejects_unsupported_upload(client) -> None:
    body = signup(client, "type@example.com")
    headers = auth_headers(body["access_token"], body["organizations"][0]["id"])
    response = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.txt", b"text", "text/plain")},
    )
    assert response.status_code == 415


def test_rejects_content_type_mismatch(client) -> None:
    body = signup(client, "scan@example.com")
    headers = auth_headers(body["access_token"], body["organizations"][0]["id"])
    response = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", b"not-a-png", "image/png")},
    )
    assert response.status_code == 400


def test_idempotent_ingest(client) -> None:
    body = signup(client, "idem@example.com")
    headers = auth_headers(body["access_token"], body["organizations"][0]["id"])
    headers["Idempotency-Key"] = "upload-1"
    first = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    second = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["batch_id"] == second.json()["batch_id"]


def test_human_review_edit_and_reject(client, settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "Corner Store\nDate: 01/09/2026",
    )
    body = signup(client, "reviewer@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)
    ingest = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    job_id = ingest.json()["jobs"][0]["job_id"]

    from app.db import get_session_factory

    session = get_session_factory()()
    try:
        process_available_jobs(session, settings)
    finally:
        session.close()

    waiting = client.get(f"/api/v2/jobs/{job_id}", headers=headers)
    assert waiting.json()["status"] == "waiting_for_review"
    expense_id = waiting.json()["expense_id"]
    expense = client.get(f"/api/v2/expenses/{expense_id}", headers=headers)
    assert expense.json()["status"] == "needs_review"

    blocked = client.post(
        f"/api/v2/expenses/{expense_id}/review",
        headers=headers,
        json={"decision": "approve"},
    )
    assert blocked.status_code == 400

    edited = client.post(
        f"/api/v2/expenses/{expense_id}/review",
        headers=headers,
        json={
            "decision": "edit",
            "merchant": "Corner Store",
            "transaction_date": "01/09/2026",
            "total": "88.50",
            "category": "shopping",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "accepted"
    assert edited.json()["total_minor_units"] == 8850
    assert edited.json()["category"] == "shopping"

    done = client.get(f"/api/v2/jobs/{job_id}", headers=headers)
    assert done.json()["status"] == "succeeded"


def test_human_review_reject(client, settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tools.extract_document_text",
        lambda content, content_type: "Corner Store\nDate: 01/09/2026",
    )
    body = signup(client, "rejector@example.com")
    org_id = body["organizations"][0]["id"]
    headers = auth_headers(body["access_token"], org_id)
    ingest = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    job_id = ingest.json()["jobs"][0]["job_id"]

    from app.db import get_session_factory

    session = get_session_factory()()
    try:
        process_available_jobs(session, settings)
    finally:
        session.close()

    expense_id = client.get(f"/api/v2/jobs/{job_id}", headers=headers).json()["expense_id"]
    rejected = client.post(
        f"/api/v2/expenses/{expense_id}/review",
        headers=headers,
        json={"decision": "reject", "reason": "Not a business expense"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert "Not a business expense" in rejected.json()["messages"]
