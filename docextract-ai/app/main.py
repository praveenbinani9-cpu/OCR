from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import render_metrics
from app.core.middleware import AuditMiddleware, RequestContextMiddleware
from app.core.rate_limit import limiter

configure_logging()
log = get_logger("main")

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", environment=settings.environment, model=settings.llm_model)
    # Ensure S3 bucket exists (idempotent)
    try:
        from app.services.storage import storage_service

        storage_service.ensure_bucket()
    except Exception as exc:
        log.warning("storage_init_failed", error=str(exc))
    yield
    log.info("shutdown")


app = FastAPI(
    title="DocExtract AI",
    description="Production-grade document intelligence SaaS for Indian GST documents.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# Middleware (registered in reverse execution order)
app.add_middleware(AuditMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

# Rate limiter
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "error": "rate_limit_exceeded",
            "detail": str(exc.detail) if hasattr(exc, "detail") else "Too many requests",
        },
    )


@app.get("/api/v1/metrics", include_in_schema=False)
def metrics_endpoint() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


app.include_router(api_router, prefix="/api/v1")
