from __future__ import annotations

from starlette.requests import Request

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def tenant_key(request: Request) -> str:
    """Use tenant_id when authenticated, else fall back to client IP."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return f"tenant:{tenant_id}"
    return f"ip:{get_remote_address(request)}"


def _resolve_storage_uri() -> str:
    """Use Redis in prod; fall back to in-memory for tests or when Redis is local-only."""
    url = settings.redis_url
    if settings.database_url.startswith("sqlite") or settings.environment == "test":
        return "memory://"
    return url


limiter = Limiter(
    key_func=tenant_key,
    default_limits=[settings.rate_limit_default],
    storage_uri=_resolve_storage_uri(),
    headers_enabled=False,
)
