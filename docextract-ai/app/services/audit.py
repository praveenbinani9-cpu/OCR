"""Audit log writer."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def write_audit(
    db: Session,
    *,
    tenant_id: str | uuid.UUID,
    user_id: str | uuid.UUID | None,
    action: str,
    resource: str,
    ip_address: str | None,
    status_code: int | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=_uuid(tenant_id),
        user_id=_uuid(user_id) if user_id else None,
        action=action[:200],
        resource=resource[:500],
        ip_address=ip_address,
        status_code=status_code,
    )
    db.add(entry)
    db.commit()


def _uuid(val: str | uuid.UUID) -> uuid.UUID:
    return val if isinstance(val, uuid.UUID) else uuid.UUID(str(val))
