
import uuid
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, require_role
from app.core.database import get_db
from app.models.review import ReviewQueue, ReviewStatus
from app.models.user import UserRole
from app.schemas.review import ReviewItemOut, ReviewUpdate

router = APIRouter()


@router.get("", response_model=List[ReviewItemOut])
def list_review_items(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
) -> List[ReviewItemOut]:
    stmt = select(ReviewQueue).where(ReviewQueue.tenant_id == principal.tenant_id)
    if status_filter:
        stmt = stmt.where(ReviewQueue.status == status_filter)
    rows = (
        db.execute(stmt.order_by(ReviewQueue.created_at.asc()).limit(limit)).scalars().all()
    )
    return [
        ReviewItemOut(
            id=str(r.id),
            extraction_id=str(r.extraction_id),
            reason=r.reason,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            reviewer_id=str(r.reviewer_id) if r.reviewer_id else None,
            reviewed_at=r.reviewed_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.patch("/{item_id}", response_model=ReviewItemOut)
def update_review_item(
    item_id: uuid.UUID,
    payload: ReviewUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role(UserRole.ADMIN, UserRole.REVIEWER))],
) -> ReviewItemOut:
    item = db.get(ReviewQueue, item_id)
    if not item or item.tenant_id != principal.tenant_id:
        raise HTTPException(404, "review_item_not_found")
    item.status = ReviewStatus(payload.status)
    item.reviewer_id = principal.user_id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return ReviewItemOut(
        id=str(item.id),
        extraction_id=str(item.extraction_id),
        reason=item.reason,
        status=item.status.value,
        reviewer_id=str(item.reviewer_id) if item.reviewer_id else None,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
    )
