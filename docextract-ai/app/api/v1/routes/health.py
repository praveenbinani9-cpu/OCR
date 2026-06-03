
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ocr import ocr_service
from app.services.storage import storage_service

router = APIRouter()


def _check_db(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    try:
        import redis  # lazy
        from app.core.config import settings

        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception:
        return False


@router.get("/health")
def health(db: Annotated[Session, Depends(get_db)]) -> dict:
    checks = {
        "database": _check_db(db),
        "redis": _check_redis(),
        "s3": storage_service.health(),
        "ocr": ocr_service.health(),
    }
    overall = all(checks.values())
    return {
        "status": "ok" if overall else "degraded",
        "checks": checks,
        "version": "1.0.0",
    }
