"""FastAPI dependencies: DB session, auth (JWT or API key), tenant resolution."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token, verify_api_key
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "unauthorized") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class Principal:
    """Authenticated principal — either a User (JWT) or an API key (machine)."""

    def __init__(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        role: UserRole,
        auth_type: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role
        self.auth_type = auth_type  # "jwt" | "api_key"


def _resolve_jwt(token: str, db: Session) -> Principal:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise _unauthorized("invalid_token") from exc
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role", UserRole.MEMBER.value)
    if not user_id or not tenant_id:
        raise _unauthorized("invalid_token_claims")
    user = db.get(User, uuid.UUID(user_id))
    if not user or str(user.tenant_id) != str(tenant_id):
        raise _unauthorized("user_not_found")
    return Principal(
        tenant_id=user.tenant_id,
        user_id=user.id,
        role=UserRole(role),
        auth_type="jwt",
    )


def _resolve_api_key(raw_key: str, db: Session) -> Principal:
    """Try every active key for the tenant prefix-less storage uses bcrypt — verify all."""
    keys = db.execute(select(APIKey)).scalars().all()
    for key in keys:
        if verify_api_key(raw_key, key.key_hash):
            key.last_used = datetime.now(timezone.utc)
            db.add(key)
            db.commit()
            return Principal(
                tenant_id=key.tenant_id,
                user_id=None,
                role=UserRole.MEMBER,
                auth_type="api_key",
            )
    raise _unauthorized("invalid_api_key")


def get_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    if x_api_key:
        principal = _resolve_api_key(x_api_key, db)
    elif creds and creds.scheme.lower() == "bearer":
        principal = _resolve_jwt(creds.credentials, db)
    else:
        raise _unauthorized("missing_credentials")

    # Surface to middleware (audit + rate-limit + logging)
    request.state.tenant_id = str(principal.tenant_id)
    request.state.user_id = str(principal.user_id) if principal.user_id else None
    request.state.auth_type = principal.auth_type
    return principal


def require_role(*roles: UserRole):
    def _checker(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.auth_type == "api_key":
            # API keys are tenant-scoped and considered MEMBER. Allow if MEMBER permitted.
            if UserRole.MEMBER in roles:
                return principal
            raise HTTPException(403, "api_key_not_allowed_for_this_action")
        if principal.role not in roles:
            raise HTTPException(403, "insufficient_role")
        return principal

    return _checker


def get_current_tenant(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Tenant:
    tenant = db.get(Tenant, principal.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    return tenant
