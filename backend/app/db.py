from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db_models import Base, Membership, Organization, User
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
    return _engine


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
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
