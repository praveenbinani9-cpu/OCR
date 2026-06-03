"""Outbound webhook dispatch."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("webhook")


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def post_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> int:
    body = json.dumps(payload, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "DocExtract-AI/1.0"}
    if secret:
        headers["X-DocExtract-Signature"] = _sign(body, secret)
    with httpx.Client(timeout=settings.webhook_timeout_seconds) as client:
        resp = client.post(url, content=body, headers=headers)
    log.info("webhook_sent", url=url, status=resp.status_code)
    resp.raise_for_status()
    return resp.status_code
