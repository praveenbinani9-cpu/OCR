"""Outbound webhook dispatch with HMAC-SHA256 signing (Stripe-style)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("webhook")

SIGNATURE_HEADER = "X-DocExtract-Signature"
TIMESTAMP_HEADER = "X-DocExtract-Timestamp"
SIGNATURE_VERSION = "v1"

# Reject signatures older than this when verifying (anti-replay).
DEFAULT_TOLERANCE_SECONDS = 300


def _sign_payload(timestamp: str, body: bytes, secret: str) -> str:
    """HMAC-SHA256 over `f"{timestamp}.{body}"`. Returns hex digest."""
    signed_payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()


def build_signature_header(timestamp: str, signature: str) -> str:
    """Stripe-style header: `t=<unix>,v1=<hex>`."""
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def post_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> int:
    body = json.dumps(payload, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "DocExtract-AI/1.0"}
    if secret:
        timestamp = str(int(time.time()))
        signature = _sign_payload(timestamp, body, secret)
        headers[SIGNATURE_HEADER] = build_signature_header(timestamp, signature)
        headers[TIMESTAMP_HEADER] = timestamp
    with httpx.Client(timeout=settings.webhook_timeout_seconds) as client:
        resp = client.post(url, content=body, headers=headers)
    log.info("webhook_sent", url=url, status=resp.status_code, signed=bool(secret))
    resp.raise_for_status()
    return resp.status_code
