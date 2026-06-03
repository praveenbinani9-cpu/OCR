"""Integration tests for API key list / rotate / revoke endpoints."""
from __future__ import annotations

import io
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
)
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from tests.fixtures.sample_invoice import SAMPLE_INVOICE_EXTRACTED, SAMPLE_INVOICE_OCR_TEXT


@pytest.fixture()
def tenant_jwt_and_key(engine):
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
    key = APIKey(
        tenant_id=tenant.id,
        key_hash=hash_api_key(raw_key),
        name="initial-key",
        rate_limit_per_minute=600,
    )
    db.add(key)
    db.commit()
    jwt = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), role=user.role.value
    )
    info = {
        "tenant_id": str(tenant.id),
        "user_id": str(user.id),
        "api_key": raw_key,
        "api_key_id": str(key.id),
        "jwt": jwt,
    }
    db.close()
    return info


def _patch_pipeline():
    storage = MagicMock()
    storage.build_key.return_value = "tenants/x/y.pdf"
    storage.upload.return_value = "tenants/x/y.pdf"
    storage.health.return_value = True

    ocr = MagicMock()
    ocr.extract_text.return_value = SAMPLE_INVOICE_OCR_TEXT

    extraction = MagicMock()
    extraction.extract = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)
    extraction.correct = AsyncMock(return_value=SAMPLE_INVOICE_EXTRACTED)
    return storage, ocr, extraction


def test_list_api_keys_returns_only_unrevoked_by_default(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    resp = client.get("/api/v1/auth/api-keys", headers=h)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "initial-key"
    assert "api_key" not in items[0]  # plaintext must never leak
    assert items[0]["revoked_at"] is None


def test_create_then_list_shows_both_keys(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    resp = client.post(
        "/api/v1/auth/api-key",
        headers={**h, "Content-Type": "application/json"},
        json={"name": "ci-key", "rate_limit_per_minute": 200},
    )
    assert resp.status_code == 201
    new_key_plain = resp.json()["api_key"]
    assert new_key_plain.startswith("dx_")

    resp = client.get("/api/v1/auth/api-keys", headers=h)
    assert {k["name"] for k in resp.json()} == {"initial-key", "ci-key"}


def test_rotate_invalidates_old_secret_and_returns_new_one(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    old_secret = tenant_jwt_and_key["api_key"]
    key_id = tenant_jwt_and_key["api_key_id"]

    storage, ocr, extraction = _patch_pipeline()
    with patch("app.api.v1.routes.extract.storage_service", storage), \
         patch("app.api.v1.routes.extract.ocr_service", ocr), \
         patch("app.api.v1.routes.extract.extraction_service", extraction):
        # Old key works before rotation
        r0 = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": old_secret},
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
        assert r0.status_code == 200

        # Rotate
        r1 = client.post(f"/api/v1/auth/api-keys/{key_id}/rotate", headers=h)
        assert r1.status_code == 200, r1.text
        new_secret = r1.json()["api_key"]
        assert new_secret.startswith("dx_")
        assert new_secret != old_secret
        assert r1.json()["id"] == key_id
        assert "rotated_at" in r1.json()

        # Old key no longer authenticates
        r2 = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": old_secret},
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
        assert r2.status_code == 401

        # New key works
        r3 = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": new_secret},
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
        assert r3.status_code == 200


def test_revoke_then_old_key_is_unauthorized(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    key_id = tenant_jwt_and_key["api_key_id"]

    r = client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=h)
    assert r.status_code == 204

    storage, ocr, extraction = _patch_pipeline()
    with patch("app.api.v1.routes.extract.storage_service", storage), \
         patch("app.api.v1.routes.extract.ocr_service", ocr), \
         patch("app.api.v1.routes.extract.extraction_service", extraction):
        r2 = client.post(
            "/api/v1/extract",
            headers={"X-API-Key": tenant_jwt_and_key["api_key"]},
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
    assert r2.status_code == 401

    # Default list hides revoked
    r3 = client.get("/api/v1/auth/api-keys", headers=h)
    assert r3.json() == []

    # include_revoked surfaces it with revoked_at populated
    r4 = client.get("/api/v1/auth/api-keys?include_revoked=true", headers=h)
    items = r4.json()
    assert len(items) == 1
    assert items[0]["revoked_at"] is not None


def test_revoke_is_idempotent(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    key_id = tenant_jwt_and_key["api_key_id"]
    assert client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=h).status_code == 204


def test_rotate_revoked_key_is_conflict(client, tenant_jwt_and_key):
    h = {"Authorization": f"Bearer {tenant_jwt_and_key['jwt']}"}
    key_id = tenant_jwt_and_key["api_key_id"]
    client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=h)
    r = client.post(f"/api/v1/auth/api-keys/{key_id}/rotate", headers=h)
    assert r.status_code == 409


def test_api_key_cannot_manage_other_api_keys(client, tenant_jwt_and_key):
    key_id = tenant_jwt_and_key["api_key_id"]
    h = {"X-API-Key": tenant_jwt_and_key["api_key"]}
    # API-key auth is rejected for key management endpoints
    assert client.get("/api/v1/auth/api-keys", headers=h).status_code == 403
    assert client.post(f"/api/v1/auth/api-keys/{key_id}/rotate", headers=h).status_code == 403
    assert client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=h).status_code == 403


def test_cannot_rotate_or_revoke_other_tenants_key(client, engine, tenant_jwt_and_key):
    # Create a second tenant
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    raw = generate_api_key()
    t2 = Tenant(
        name=f"Other-{secrets.token_hex(3)}",
        api_key_hash=hash_api_key(raw),
        plan="free",
        rate_limit=60,
    )
    db.add(t2)
    db.flush()
    u2 = User(
        tenant_id=t2.id,
        email=f"u-{secrets.token_hex(3)}@other.test",
        password_hash=hash_password("Password!123"),
        role=UserRole.ADMIN,
        jwt_secret=secrets.token_urlsafe(32),
    )
    db.add(u2)
    db.commit()
    jwt2 = create_access_token(
        subject=str(u2.id), tenant_id=str(t2.id), role=u2.role.value
    )
    db.close()

    # tenant2 JWT trying to mutate tenant1's key
    target_id = tenant_jwt_and_key["api_key_id"]
    h2 = {"Authorization": f"Bearer {jwt2}"}
    assert client.post(f"/api/v1/auth/api-keys/{target_id}/rotate", headers=h2).status_code == 404
    assert client.delete(f"/api/v1/auth/api-keys/{target_id}", headers=h2).status_code == 404
