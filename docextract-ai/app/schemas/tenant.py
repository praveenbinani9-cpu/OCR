from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)
    plan: str = "free"
    rate_limit: int = Field(default=60, ge=1, le=100000)


class TenantOut(BaseModel):
    id: str
    name: str
    plan: str
    rate_limit: int


class TenantUsage(BaseModel):
    tenant_id: str
    documents_total: int
    documents_today: int
    extractions_total: int
    extractions_today: int
    review_queue_size: int
    plan: str
    rate_limit: int


class WebhookSecretOut(BaseModel):
    configured: bool


class WebhookSecretCreated(BaseModel):
    secret: str = Field(description="Plaintext webhook secret. Shown once. Store securely.")
    created_at: datetime
