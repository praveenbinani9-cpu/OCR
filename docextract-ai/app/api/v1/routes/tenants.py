from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.database import get_db
from app.core.metrics import REVIEW_QUEUE_SIZE
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.review import ReviewQueue, ReviewStatus
from app.models.tenant import Tenant
from app.schemas.tenant import (
    TenantUsage,
    WebhookSecretCreated,
    WebhookSecretOut,
)
from app.services.webhook import _sign_payload  # noqa: F401  (re-exported via helper below)
import secrets

router = APIRouter()


def _require_admin_or_jwt(principal: Principal) -> None:
    if principal.auth_type != "jwt":
        raise HTTPException(403, "api_key_cannot_manage_webhook_secret")


@router.get("/usage", response_model=TenantUsage)
def tenant_usage(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> TenantUsage:
    tenant = db.get(Tenant, principal.tenant_id)
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    docs_total = db.execute(
        select(func.count(Document.id)).where(Document.tenant_id == principal.tenant_id)
    ).scalar_one()
    docs_today = db.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == principal.tenant_id,
            Document.created_at >= today_start,
        )
    ).scalar_one()
    ex_total = db.execute(
        select(func.count(Extraction.id)).where(
            Extraction.tenant_id == principal.tenant_id
        )
    ).scalar_one()
    ex_today = db.execute(
        select(func.count(Extraction.id)).where(
            Extraction.tenant_id == principal.tenant_id,
            Extraction.created_at >= today_start,
        )
    ).scalar_one()
    review_size = db.execute(
        select(func.count(ReviewQueue.id)).where(
            ReviewQueue.tenant_id == principal.tenant_id,
            ReviewQueue.status == ReviewStatus.PENDING,
        )
    ).scalar_one()

    REVIEW_QUEUE_SIZE.set(int(review_size))

    return TenantUsage(
        tenant_id=str(principal.tenant_id),
        documents_total=int(docs_total),
        documents_today=int(docs_today),
        extractions_total=int(ex_total),
        extractions_today=int(ex_today),
        review_queue_size=int(review_size),
        plan=tenant.plan if tenant else "free",
        rate_limit=tenant.rate_limit if tenant else 60,
    )


@router.get("/webhook-secret", response_model=WebhookSecretOut)
def get_webhook_secret_status(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> WebhookSecretOut:
    """Return whether a webhook secret is configured (never returns the secret itself)."""
    _require_admin_or_jwt(principal)
    tenant = db.get(Tenant, principal.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    return WebhookSecretOut(configured=bool(tenant.webhook_secret))


@router.post("/webhook-secret/rotate", response_model=WebhookSecretCreated)
def rotate_webhook_secret(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> WebhookSecretCreated:
    """Generate and store a new webhook secret. Plaintext shown once.

    All future outbound webhooks for this tenant will be HMAC-SHA256 signed
    with this secret. Existing signed payloads cannot be verified after rotation —
    rotate only when ready to update your receiver.
    """
    _require_admin_or_jwt(principal)
    tenant = db.get(Tenant, principal.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    new_secret = f"whsec_{secrets.token_urlsafe(32)}"
    tenant.webhook_secret = new_secret
    db.commit()
    return WebhookSecretCreated(
        secret=new_secret,
        created_at=datetime.now(timezone.utc),
    )


@router.delete("/webhook-secret", status_code=204)
def delete_webhook_secret(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    """Disable webhook signing (subsequent webhooks will be unsigned)."""
    _require_admin_or_jwt(principal)
    tenant = db.get(Tenant, principal.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    if tenant.webhook_secret is not None:
        tenant.webhook_secret = None
        db.commit()
    return None


# unused but kept for type checkers
_ = timedelta
