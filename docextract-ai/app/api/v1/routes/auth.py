
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    verify_password,
)
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.auth import APIKeyCreate, APIKeyCreated, TokenRequest, TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,  # required by slowapi
    payload: TokenRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role.value,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_minutes * 60)


@router.post("/api-key", response_model=APIKeyCreated, status_code=201)
def create_api_key(
    payload: APIKeyCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> APIKeyCreated:
    if principal.auth_type != "jwt":
        raise HTTPException(403, "api_key_cannot_mint_api_keys")
    raw = generate_api_key()
    entry = APIKey(
        tenant_id=principal.tenant_id,
        key_hash=hash_api_key(raw),
        name=payload.name,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return APIKeyCreated(
        id=str(entry.id),
        name=entry.name,
        api_key=raw,
        rate_limit_per_minute=entry.rate_limit_per_minute,
    )


# Static fallback to keep secrets module usage if needed by linters
_ = secrets.token_hex(1)
