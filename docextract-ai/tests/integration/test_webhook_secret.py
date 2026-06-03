"""Integration tests for tenant webhook secret rotation + outbound signature."""
from __future__ import annotations

import secrets
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, hash_password
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.core.security import generate_api_key, hash_api_key


@pytest.fixture()
def jwt_admin(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    raw = generate_api_key()
    tenant = Tenant(
        name=f"WebhookCo-{secrets.token_hex(3)}",
        api_key_hash=hash_api_key(raw),
        plan="pro",
        rate_limit=600,
    )
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"wh-{secrets.token_hex(3)}@co.test",
        password_hash=hash_password("Password!123"),
        role=UserRole.ADMIN,
        jwt_secret=secrets.token_urlsafe(32),
    )
    db.add(user)
    db.add(APIKey(tenant_id=tenant.id, key_hash=hash_api_key(raw), name="k", rate_limit_per_minute=600))
    db.commit()
    jwt = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), role=user.role.value
    )
    out = {"tenant_id": str(tenant.id), "api_key": raw, "jwt": jwt}
    db.close()
    return out


def test_webhook_secret_initially_not_configured(client, jwt_admin):
    h = {"Authorization": f"Bearer {jwt_admin['jwt']}"}
    r = client.get("/api/v1/tenants/webhook-secret", headers=h)
    assert r.status_code == 200
    assert r.json() == {"configured": False}


def test_rotate_creates_new_secret_and_status_reports_configured(client, jwt_admin):
    h = {"Authorization": f"Bearer {jwt_admin['jwt']}"}
    r1 = client.post("/api/v1/tenants/webhook-secret/rotate", headers=h)
    assert r1.status_code == 200
    secret1 = r1.json()["secret"]
    assert secret1.startswith("whsec_")

    r2 = client.get("/api/v1/tenants/webhook-secret", headers=h)
    assert r2.json() == {"configured": True}

    # Rotate again → new value, status remains configured
    r3 = client.post("/api/v1/tenants/webhook-secret/rotate", headers=h)
    assert r3.status_code == 200
    secret2 = r3.json()["secret"]
    assert secret2 != secret1


def test_delete_webhook_secret(client, jwt_admin):
    h = {"Authorization": f"Bearer {jwt_admin['jwt']}"}
    client.post("/api/v1/tenants/webhook-secret/rotate", headers=h)
    r = client.delete("/api/v1/tenants/webhook-secret", headers=h)
    assert r.status_code == 204
    assert client.get("/api/v1/tenants/webhook-secret", headers=h).json() == {"configured": False}


def test_api_key_auth_cannot_manage_webhook_secret(client, jwt_admin):
    h = {"X-API-Key": jwt_admin["api_key"]}
    assert client.get("/api/v1/tenants/webhook-secret", headers=h).status_code == 403
    assert client.post("/api/v1/tenants/webhook-secret/rotate", headers=h).status_code == 403
    assert client.delete("/api/v1/tenants/webhook-secret", headers=h).status_code == 403
