"""Celery application + queue routing + beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "docextract",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    task_routes={
        "app.workers.tasks.process_document": {"queue": "document_processing"},
        "app.workers.tasks.send_webhook": {"queue": "notifications"},
        "app.workers.tasks.cleanup_old_files": {"queue": "notifications"},
    },
    task_default_queue="document_processing",
    beat_schedule={
        "cleanup-old-files": {
            "task": "app.workers.tasks.cleanup_old_files",
            "schedule": crontab(minute=0, hour=3),  # daily 03:00 UTC
        },
    },
)
