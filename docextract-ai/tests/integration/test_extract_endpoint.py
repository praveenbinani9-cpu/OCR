"""Integration test for /api/v1/extract. OCR + LLM + S3 are mocked."""
from __future__ import annotations

import io
import json
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import generate_api_key, hash_api_key, hash_password
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from tests.fixtures.sample_invoice import SAMPLE_INVOICE_EXTRACTED, SAMPLE_INVOICE_OCR_TEXT


@pytest.fixture()
def tenant_with_key(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    raw_key = generate_api_key()
    tenant = Tenant(
        name=f"Acme-{secrets.token_hex(4)}",
        api_key_hash=hash_api_key(raw_key),
        plan="pro",
        rate_limit=600,
    )
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"admin-{secrets.token_hex(3)}@acme.test",
        password_hash=hash_password("Password!123"),
        role=UserRole.ADMIN,
        jwt_secret=secrets.token_urlsafe(32),
    )
    db.add(user)
    db.add(
        APIKey(
            tenant_id=tenant.id,
            key_hash=hash_api_key(raw_key),
            name="test",
            rate_limit_per_minute=600,
        )
    )
    db.commit()
    info = {"tenant_id": str(tenant.id), "user_id": str(user.id), "api_key": raw_key}
    db.close()
    return info


def _patch_pipeline():
    storage_mock = MagicMock()
    storage_mock.build_key.return_value = "tenants/x/documents/y.pdf"
    storage_mock.upload.return_value = "tenants/x/documents/y.pdf"
    storage_mock.health.return_value = True

    ocr_mock = MagicMock()
    ocr_mock.extract_text.return_value = SAMPLE_INVOICE_OCR_TEXT

    extraction_mock = MagicMock()
    extraction_mock.extract = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)
    extraction_mock.correct = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)

    return storage_mock, ocr_mock, extraction_mock


def test_extract_endpoint_returns_full_schema(client, tenant_with_key):
    storage_mock, ocr_mock, extraction_mock = _patch_pipeline()

    with patch("app.api.v1.routes.extract.storage_service", storage_mock), \
         patch("app.api.v1.routes.extract.ocr_service", ocr_mock), \
         patch("app.api.v1.routes.extract.extraction_service", extraction_mock):
        resp = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": tenant_with_key["api_key"]},
            files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["document_type"] == "TAX_INVOICE"
    assert body["data"]["vendor_gstin"]["value"] == "27AABCU9603R1ZX"
    assert body["validation"]["gstin_valid"] is True
    assert body["validation"]["amounts_reconciled"] is True
    assert body["review_required"] is False


def test_extract_rejects_unsupported_media(client, tenant_with_key):
    resp = client.post(
        "/api/v1/extract",
        headers={"X-API-Key": tenant_with_key["api_key"]},
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 415


def test_extract_requires_auth(client):
    resp = client.post(
        "/api/v1/extract",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code == 401


# Avoid unused import warning
_ = json
