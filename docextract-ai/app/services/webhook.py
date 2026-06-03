"""Outbound webhook dispatch with HMAC-SHA256 signing (Stripe-style)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("webhook")

SIGNATURE_HEADER = "X-DocExtract-Signature"
TIMESTAMP_HEADER = "X-DocExtract-Timestamp"
SIGNATURE_VERSION = "v1"

# Reject signatures older than this when verifying (anti-replay).
DEFAULT_TOLERANCE_SECONDS = 300

# Response bodies can be huge — keep an excerpt only.
RESPONSE_BODY_LIMIT = 4096


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of a single HTTP attempt against the receiver."""

    status_code: int | None
    body_excerpt: str
    ok: bool
    error: str | None = None


def _sign_payload(timestamp: str, body: bytes, secret: str) -> str:
    signed_payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()


def build_signature_header(timestamp: str, signature: str) -> str:
    return f"t={timestamp},{SIGNATURE_VERSION}={signature}"


def verify_signature(
    body: bytes,
    header_value: str,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """Verify an incoming webhook signature header.

    Header format: `t=<unix>,v1=<hex>`. Returns True iff:
      1. Timestamp is within ``tolerance_seconds`` of now (anti-replay).
      2. HMAC-SHA256(`f"{t}.{body}"`, secret) matches v1 in constant time.
    """
    if not header_value or not secret:
        return False
    parts = {}
    for piece in header_value.split(","):
        if "=" in piece:
            k, v = piece.strip().split("=", 1)
            parts[k] = v
    timestamp = parts.get("t")
    received = parts.get(SIGNATURE_VERSION)
    if not timestamp or not received:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > tolerance_seconds:
        return False
    expected = _sign_payload(timestamp, body, secret)
    return hmac.compare_digest(expected, received)


def deliver(url: str, payload: dict[str, Any], secret: str | None = None) -> DeliveryResult:
    """Send a webhook (no retry — caller / Celery owns the retry loop).

    Always returns a ``DeliveryResult``. Never raises for connection / non-2xx;
    callers inspect ``ok`` to decide whether to retry.
    """
    body = json.dumps(payload, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "DocExtract-AI/1.0"}
    if secret:
        timestamp = str(int(time.time()))
        signature = _sign_payload(timestamp, body, secret)
        headers[SIGNATURE_HEADER] = build_signature_header(timestamp, signature)
        headers[TIMESTAMP_HEADER] = timestamp
    try:
        with httpx.Client(timeout=settings.webhook_timeout_seconds) as client:
            resp = client.post(url, content=body, headers=headers)
        excerpt = resp.text[:RESPONSE_BODY_LIMIT] if resp.text else ""
        ok = 200 <= resp.status_code < 300
        log.info(
            "webhook_attempt",
            url=url,
            status=resp.status_code,
            ok=ok,
            signed=bool(secret),
        )
        return DeliveryResult(
            status_code=resp.status_code, body_excerpt=excerpt, ok=ok
        )
    except Exception as exc:
        log.warning("webhook_transport_error", url=url, error=str(exc))
        return DeliveryResult(
            status_code=None,
            body_excerpt="",
            ok=False,
            error=str(exc)[:RESPONSE_BODY_LIMIT],
        )


def post_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> int:
    """Legacy thin wrapper: raises on failure, returns status on success.

    Preserved for older callers / docs. Prefer ``deliver()`` directly.
    """
    result = deliver(url, payload, secret=secret)
    if not result.ok:
        raise RuntimeError(
            f"webhook_failed: status={result.status_code} error={result.error}"
        )
    assert result.status_code is not None
    return result.status_code
