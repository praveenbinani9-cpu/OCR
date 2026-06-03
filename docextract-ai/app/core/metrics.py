from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

REQUESTS_TOTAL = Counter(
    "docextract_requests_total",
    "Total API requests",
    labelnames=("method", "endpoint", "status"),
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "docextract_request_latency_seconds",
    "Request latency in seconds",
    labelnames=("method", "endpoint"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32),
    registry=REGISTRY,
)

EXTRACTION_LATENCY = Histogram(
    "docextract_extraction_latency_seconds",
    "End-to-end extraction latency",
    labelnames=("document_type",),
    buckets=(0.5, 1, 2, 4, 8, 16, 32, 64),
    registry=REGISTRY,
)

CONFIDENCE_HIST = Histogram(
    "docextract_confidence",
    "Overall extraction confidence distribution",
    labelnames=("document_type",),
    buckets=(0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.99, 1.0),
    registry=REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "docextract_queue_depth",
    "Pending tasks in Celery queue",
    labelnames=("queue",),
    registry=REGISTRY,
)

REVIEW_QUEUE_SIZE = Gauge(
    "docextract_review_queue_size",
    "Items pending human review",
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
