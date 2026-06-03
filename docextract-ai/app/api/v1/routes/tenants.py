
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.database import get_db
from app.core.metrics import REVIEW_QUEUE_SIZE
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.review import ReviewQueue, ReviewStatus
from app.models.tenant import Tenant
from app.schemas.tenant import TenantUsage

router = APIRouter()


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


# unused but kept for type checkers
_ = timedelta
