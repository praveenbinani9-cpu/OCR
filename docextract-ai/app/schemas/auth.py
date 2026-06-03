from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)


class APIKeyCreated(BaseModel):
    id: str
    name: str
    api_key: str = Field(description="Plaintext key — shown once. Store securely.")
    rate_limit_per_minute: int


class APIKeyOut(BaseModel):
    """Safe representation — never includes plaintext key."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    rate_limit_per_minute: int
    last_used: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class APIKeyRotated(APIKeyCreated):
    """Returned by POST /auth/api-keys/{id}/rotate. Plaintext shown once."""

    rotated_at: datetime
