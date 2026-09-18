from app.db import get_session_factory
from app.security import create_access_token
from tests.conftest import PNG_BYTES, add_member, auth_headers, signup


def test_cross_tenant_job_is_hidden(client) -> None:
    first = signup(client, "a@example.com", organization="Alpha")
    second = signup(client, "b@example.com", organization="Beta")
    alpha_headers = auth_headers(first["access_token"], first["organizations"][0]["id"])
    beta_headers = auth_headers(second["access_token"], second["organizations"][0]["id"])

    ingest = client.post(
        "/api/v2/receipts",
        headers=alpha_headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    job_id = ingest.json()["jobs"][0]["job_id"]

    hidden = client.get(f"/api/v2/jobs/{job_id}", headers=beta_headers)
    assert hidden.status_code == 404

    visible = client.get(f"/api/v2/jobs/{job_id}", headers=alpha_headers)
    assert visible.status_code == 200


def test_member_cannot_read_another_members_job(client, settings) -> None:
    owner = signup(client, "owner-iso@example.com", organization="Gamma")
    org_id = owner["organizations"][0]["id"]
    session = get_session_factory()()
    try:
        member = add_member(session, org_id, "member-iso@example.com", "member")
    finally:
        session.close()
    member_token = create_access_token(
        member.id, member.email, settings.jwt_secret, settings.jwt_expire_minutes
    )
    owner_headers = auth_headers(owner["access_token"], org_id)
    member_headers = auth_headers(member_token, org_id)

    ingest = client.post(
        "/api/v2/receipts",
        headers=owner_headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    job_id = ingest.json()["jobs"][0]["job_id"]

    denied = client.get(f"/api/v2/jobs/{job_id}", headers=member_headers)
    assert denied.status_code == 404


def test_auditor_cannot_upload(client, settings) -> None:
    owner = signup(client, "owner-aud@example.com", organization="Delta")
    org_id = owner["organizations"][0]["id"]
    session = get_session_factory()()
    try:
        auditor = add_member(session, org_id, "auditor@example.com", "auditor")
    finally:
        session.close()
    token = create_access_token(
        auditor.id, auditor.email, settings.jwt_secret, settings.jwt_expire_minutes
    )
    headers = auth_headers(token, org_id)
    response = client.post(
        "/api/v2/receipts",
        headers=headers,
        files={"files": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 403
