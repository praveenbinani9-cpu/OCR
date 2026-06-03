"""Celery tasks: document processing, webhook delivery, cleanup."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.core.database import db_session
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.tenant import Tenant
from app.services.storage import storage_service
from app.services.webhook import post_webhook
from app.workers.celery_app import celery_app

log = get_logger("worker")


@celery_app.task(name="app.workers.tasks.process_document", bind=True, max_retries=3)
def process_document(self, document_id: str, webhook_url: str | None = None) -> dict:
    """Process a document asynchronously through OCR -> LLM -> validation pipeline."""
    from app.api.v1.routes.extract import _run_extraction_pipeline  # avoid cycle

    start = time.perf_counter()
    with db_session() as db:
        doc = db.get(Document, uuid.UUID(document_id))
        if not doc:
            log.warning("worker_document_missing", document_id=document_id)
            return {"status": "error", "error": "document_not_found"}
        doc.status = DocumentStatus.PROCESSING
        db.commit()
        try:
            raw = storage_service.download(doc.s3_key)
            response = asyncio.run(_run_extraction_pipeline(db, doc, raw, doc.mime_type))
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            response.processing_time_ms = elapsed_ms

            if webhook_url:
                tenant = db.get(Tenant, doc.tenant_id)
                secret = tenant.webhook_secret if tenant else None
                send_webhook.delay(webhook_url, response.model_dump(), secret)
            return response.model_dump()
        except Exception as exc:
            doc.status = DocumentStatus.FAILED
            db.commit()
            log.error("worker_extract_failed", document_id=document_id, error=str(exc))
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.send_webhook", bind=True, max_retries=5)
def send_webhook(self, url: str, payload: dict, secret: str | None = None) -> dict:
    try:
        status = post_webhook(url, payload, secret=secret)
        return {"status": "delivered", "http_status": status}
    except Exception as exc:
        log.warning("webhook_retry", url=url, attempt=self.request.retries, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.cleanup_old_files")
def cleanup_old_files(days: int = 90) -> dict:
    """Purge raw S3 objects for documents older than `days` (keeps DB records)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = 0
    with db_session() as db:
        from sqlalchemy import select

        rows = db.execute(
            select(Document).where(Document.created_at < cutoff)
        ).scalars().all()
        for doc in rows:
            try:
                storage_service.delete(doc.s3_key)
                deleted += 1
            except Exception as exc:  # pragma: no cover
                log.warning("cleanup_delete_failed", key=doc.s3_key, error=str(exc))
    log.info("cleanup_done", deleted=deleted, cutoff=cutoff.isoformat())
    return {"deleted": deleted}
