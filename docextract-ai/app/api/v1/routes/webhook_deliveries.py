"""GET /api/v1/webhook-deliveries — debug log of outbound webhook attempts."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.database import get_db
from app.models.webhook_delivery import WebhookDelivery
from app.schemas.webhook_delivery import WebhookDeliveryOut, WebhookDeliveryPage

router = APIRouter()


@router.get("", response_model=WebhookDeliveryPage)
def list_webhook_deliveries(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    document_id: uuid.UUID = Query(..., description="Filter to a specific document"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> WebhookDeliveryPage:
    """List webhook delivery attempts for a document owned by the caller's tenant.

    Returns one row per attempt, ordered newest first. Use this to debug why
    a webhook isn't reaching your receiver — `response_status`, `response_body`
    (excerpt, max 4 KB), and `attempt_count` are populated for every attempt.
    """
    stmt = select(WebhookDelivery).where(
        WebhookDelivery.tenant_id == principal.tenant_id,
        WebhookDelivery.document_id == document_id,
    )
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(WebhookDelivery.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return WebhookDeliveryPage(
        items=[
            WebhookDeliveryOut(
                id=str(r.id),
                document_id=str(r.document_id),
                url=r.url,
                response_status=r.response_status,
                response_body=r.response_body,
                attempt_count=r.attempt_count,
                delivered_at=r.delivered_at,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )
