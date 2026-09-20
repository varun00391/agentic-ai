from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.db_models import Membership, Organization, User
from app.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)

WRITE_ROLES = {"owner", "admin", "approver", "member"}
READ_ALL_ROLES = {"owner", "admin", "approver", "auditor"}


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization
    membership: Membership
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials, settings.jwt_secret)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_auth_context(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    x_organization_id: str | None = Header(default=None, alias="X-Organization-Id"),
) -> AuthContext:
    if not x_organization_id:
        raise HTTPException(
            status_code=400,
            detail="X-Organization-Id header is required",
        )
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == x_organization_id,
        )
    )
    organization = session.get(Organization, x_organization_id)
    if membership is None or organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return AuthContext(
        user=user,
        organization=organization,
        membership=membership,
        role=membership.role,
    )


def require_roles(*roles: str):
    def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if auth.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return auth

    return dependency
