from collections.abc import Generator

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db_models import Base, Membership, Organization, OrganizationPolicy, User
from app.policy import default_policy_values
from app.security import hash_password, slugify


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def create_db_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, future=True, connect_args=connect_args)


def init_engine(settings: Settings) -> Engine:
    global _engine, _SessionLocal
    _engine = create_db_engine(settings.database_url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(_engine)
    _ensure_expense_columns(_engine)
    return _engine


def _ensure_expense_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("expenses")}
    statements: list[str] = []
    if "extraction_confidence" not in columns:
        statements.append(
            "ALTER TABLE expenses ADD COLUMN extraction_confidence FLOAT"
        )
    if "extraction_source" not in columns:
        statements.append(
            "ALTER TABLE expenses ADD COLUMN extraction_source VARCHAR(16)"
        )
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database engine is not initialized")
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def bootstrap_if_needed(settings: Settings) -> None:
    if not settings.bootstrap_email or not settings.bootstrap_password:
        return
    session = get_session_factory()()
    try:
        existing = session.scalar(
            select(User).where(User.email == settings.bootstrap_email.casefold())
        )
        if existing is not None:
            return
        user = User(
            email=settings.bootstrap_email.casefold(),
            password_hash=hash_password(settings.bootstrap_password),
            display_name="Owner",
        )
        organization = Organization(
            name=settings.bootstrap_organization,
            slug=slugify(settings.bootstrap_organization),
        )
        session.add_all([user, organization])
        session.flush()
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        session.add(
            OrganizationPolicy(
                organization_id=organization.id,
                **default_policy_values(settings),
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
