from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


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
