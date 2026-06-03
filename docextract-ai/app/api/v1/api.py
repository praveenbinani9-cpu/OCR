from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import auth, documents, extract, health, review, tenants

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(extract.router, tags=["extract"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(review.router, prefix="/review-queue", tags=["review"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
