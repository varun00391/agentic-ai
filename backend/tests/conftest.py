import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import app
from app.config import Settings, get_settings
from app.db import get_session_factory, init_engine
from app.db_models import Membership, User
from app.security import hash_password


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
RECEIPT_TEXT = """
Fresh Mart
Date: 01/09/2026
Grand Total: INR 123.45
"""

STATEMENT_TEXT = """
Paid to
SHARMA MEDICAL STORE
₹337
31 August
Debited from
Paid to
SANJEEV KUMAR
₹144
31 August
Debited from
Paid to
ZEEVA HEALTHCARE
₹3,800
31 August
Debited from
Paid to
ZEEVA HEALTHCARE
₹600
31 August
Debited from
Paid to
AHSAN TEA SHOP
₹208
31 August
Debited from
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'expense-v2.db'}",
        jwt_secret="test-secret-key",
        object_storage_path=tmp_path / "objects",
        planner="rule_based",
        groq_api_key=None,
        bootstrap_email=None,
        bootstrap_password=None,
        max_agent_steps=80,
        max_tool_retries=2,
    )


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.get_settings", lambda: settings)
    monkeypatch.setattr("app.deps.get_settings", lambda: settings)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def db_session(settings: Settings) -> Session:
    init_engine(settings)
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def signup(
    client: TestClient,
    email: str,
    password: str = "password123",
    organization: str = "Acme",
    name: str = "Owner",
) -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={
            "email": email,
            "password": password,
            "display_name": name,
            "organization_name": organization,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(token: str, organization_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-Id": organization_id,
    }


def add_member(
    session: Session,
    organization_id: str,
    email: str,
    role: str,
    password: str = "password123",
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=email,
    )
    session.add(user)
    session.flush()
    session.add(
        Membership(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
        )
    )
    session.commit()
    return user
