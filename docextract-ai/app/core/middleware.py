from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import REQUEST_LATENCY, REQUESTS_TOTAL

log = structlog.get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request_id, log structured access entry, record metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        endpoint = request.url.path
        method = request.method
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
            REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status=str(status_code)
            ).inc()
            log.info(
                "request",
                method=method,
                path=endpoint,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
                tenant_id=getattr(request.state, "tenant_id", None),
                user_id=getattr(request.state, "user_id", None),
            )
            structlog.contextvars.clear_contextvars()


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist audit log for mutating operations on authenticated requests."""

    AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        if (
            request.method in self.AUDITED_METHODS
            and getattr(request.state, "tenant_id", None)
            and response.status_code < 500
        ):
            try:
                from app.core.database import db_session
                from app.services.audit import write_audit

                with db_session() as db:
                    write_audit(
                        db,
                        tenant_id=request.state.tenant_id,
                        user_id=getattr(request.state, "user_id", None),
                        action=f"{request.method} {request.url.path}",
                        resource=request.url.path,
                        ip_address=request.client.host if request.client else None,
                        status_code=response.status_code,
                    )
            except Exception as exc:  # pragma: no cover - audit must not break response
                log.warning("audit_failed", error=str(exc))
        return response
