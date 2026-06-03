"""Ensure tenant A cannot read tenant B's documents/extractions."""
from __future__ import annotations

import io
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import generate_api_key, hash_api_key, hash_password
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from tests.fixtures.sample_invoice import SAMPLE_INVOICE_EXTRACTED, SAMPLE_INVOICE_OCR_TEXT


def _make_tenant(engine, name: str) -> dict:
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    raw = generate_api_key()
    t = Tenant(name=name, api_key_hash=hash_api_key(raw), plan="free", rate_limit=600)
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=f"u-{secrets.token_hex(3)}@{name}.test",
        password_hash=hash_password("Password!123"),
        role=UserRole.ADMIN,
        jwt_secret=secrets.token_urlsafe(32),
    )
    db.add(u)
    db.add(APIKey(tenant_id=t.id, key_hash=hash_api_key(raw), name="k", rate_limit_per_minute=600))
    db.commit()
    info = {"tenant_id": str(t.id), "api_key": raw}
    db.close()
    return info


@pytest.fixture()
def two_tenants(engine):
    return _make_tenant(engine, "alpha"), _make_tenant(engine, "beta")


def test_tenant_cannot_access_other_tenant_document(client, two_tenants):
    alpha, beta = two_tenants

    storage_mock = MagicMock()
    storage_mock.build_key.return_value = "tenants/x/documents/y.pdf"
    storage_mock.upload.return_value = "tenants/x/documents/y.pdf"

    ocr_mock = MagicMock()
    ocr_mock.extract_text.return_value = SAMPLE_INVOICE_OCR_TEXT

    extraction_mock = MagicMock()
    extraction_mock.extract = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)
    extraction_mock.correct = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)

    with patch("app.api.v1.routes.extract.storage_service", storage_mock), \
         patch("app.api.v1.routes.extract.ocr_service", ocr_mock), \
         patch("app.api.v1.routes.extract.extraction_service", extraction_mock):
        resp = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": alpha["api_key"]},
            files={"file": ("invoice.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
    assert resp.status_code == 200
    document_id = resp.json()["document_id"]

    # Beta tries to read alpha's document
    resp_beta = client.get(
        f"/api/v1/documents/{document_id}",
        headers={"X-API-Key": beta["api_key"]},
    )
    assert resp_beta.status_code == 404

    # Beta sees zero docs in its own list
    resp_list = client.get(
        "/api/v1/documents",
        headers={"X-API-Key": beta["api_key"]},
    )
    assert resp_list.status_code == 200
    assert resp_list.json()["total"] == 0


def test_invalid_api_key_rejected(client):
    resp = client.get(
        "/api/v1/documents",
        headers={"X-API-Key": "dx_invalid_key_value"},
    )
    assert resp.status_code == 401


# avoid unused
_ = uuid
