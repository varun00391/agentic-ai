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
