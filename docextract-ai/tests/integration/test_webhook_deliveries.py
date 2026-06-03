"""Integration tests for webhook_deliveries logging + GET endpoint."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
)
from app.models.api_key import APIKey
from app.models.document import Document, DocumentStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.webhook_delivery import WebhookDelivery
from app.services.webhook import DeliveryResult


@pytest.fixture()
def tenant_with_document(engine):
    """Two tenants, each with one document. Returns context for both."""
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    def _mk_tenant(name: str) -> dict:
        raw = generate_api_key()
        t = Tenant(name=name, api_key_hash=hash_api_key(raw), plan="pro", rate_limit=600)
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
        doc = Document(
            tenant_id=t.id,
            filename="invoice.pdf",
            s3_key=f"tenants/{t.id}/x.pdf",
            file_size=1024,
            mime_type="application/pdf",
            status=DocumentStatus.COMPLETED,
        )
        db.add(doc)
        db.commit()
        jwt = create_access_token(
            subject=str(u.id), tenant_id=str(t.id), role=u.role.value
        )
        return {
            "tenant_id": str(t.id),
            "doc_id": str(doc.id),
            "api_key": raw,
            "jwt": jwt,
        }

    alpha = _mk_tenant("alpha")
    beta = _mk_tenant("beta")
    db.close()
    return alpha, beta


def _seed_delivery(
    engine,
    *,
    tenant_id: str,
    document_id: str,
    status: int | None,
    body: str,
    attempt: int,
    delivered: bool,
) -> str:
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    row = WebhookDelivery(
        tenant_id=uuid.UUID(tenant_id),
        document_id=uuid.UUID(document_id),
        url="https://receiver.test/hook",
        response_status=status,
        response_body=body,
        attempt_count=attempt,
        delivered_at=datetime.now(timezone.utc) if delivered else None,
    )
    db.add(row)
    db.commit()
    rid = str(row.id)
    db.close()
    return rid


def test_list_webhook_deliveries_returns_tenant_rows_only(client, engine, tenant_with_document):
    alpha, beta = tenant_with_document
    _seed_delivery(
        engine, tenant_id=alpha["tenant_id"], document_id=alpha["doc_id"],
        status=200, body='{"ok":true}', attempt=1, delivered=True,
    )
    _seed_delivery(
        engine, tenant_id=beta["tenant_id"], document_id=beta["doc_id"],
        status=500, body="boom", attempt=1, delivered=False,
    )

    # Alpha sees only its own row
    r = client.get(
        f"/api/v1/webhook-deliveries?document_id={alpha['doc_id']}",
        headers={"X-API-Key": alpha["api_key"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["response_status"] == 200
    assert body["items"][0]["delivered_at"] is not None

    # Beta cannot see alpha's deliveries by passing alpha's doc_id
    r2 = client.get(
        f"/api/v1/webhook-deliveries?document_id={alpha['doc_id']}",
        headers={"X-API-Key": beta["api_key"]},
    )
    assert r2.status_code == 200
    assert r2.json()["total"] == 0


def test_list_orders_newest_first_and_paginates(client, engine, tenant_with_document):
    alpha, _ = tenant_with_document
    for i in range(3):
        _seed_delivery(
            engine, tenant_id=alpha["tenant_id"], document_id=alpha["doc_id"],
            status=500 if i < 2 else 200, body=f"attempt-{i+1}",
            attempt=i + 1, delivered=i == 2,
        )

    r = client.get(
        f"/api/v1/webhook-deliveries?document_id={alpha['doc_id']}&page=1&page_size=2",
        headers={"X-API-Key": alpha["api_key"]},
    )
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # newest first → attempt 3 first
    assert body["items"][0]["attempt_count"] == 3
    assert body["items"][0]["response_status"] == 200


def test_endpoint_requires_document_id_param(client, tenant_with_document):
    alpha, _ = tenant_with_document
    r = client.get(
        "/api/v1/webhook-deliveries",
        headers={"X-API-Key": alpha["api_key"]},
    )
    assert r.status_code == 422  # missing required query param


def test_endpoint_requires_auth(client, tenant_with_document):
    alpha, _ = tenant_with_document
    r = client.get(f"/api/v1/webhook-deliveries?document_id={alpha['doc_id']}")
    assert r.status_code == 401


def test_send_webhook_task_records_delivery_row(engine, tenant_with_document, monkeypatch):
    """Drive send_webhook synchronously (apply()) and assert a row is written."""
    from app.core import database as core_db
    from app.workers import tasks as worker_tasks

    alpha, _ = tenant_with_document

    # Point both module-level SessionLocal to the test engine so the worker's
    # db_session() lands in the same in-memory DB the test inspects.
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(core_db, "SessionLocal", TestingSession)

    # Patch deliver() to return a controlled success
    with patch.object(
        worker_tasks,
        "deliver",
        return_value=DeliveryResult(status_code=200, body_excerpt='{"ok":1}', ok=True),
    ):
        result = worker_tasks.send_webhook.apply(
            args=[
                "https://receiver.test/hook",
                {"document_id": alpha["doc_id"]},
                None,
                alpha["doc_id"],
                alpha["tenant_id"],
            ]
        ).get(disable_sync_subtasks=False)

    assert result["status"] == "delivered"
    assert result["http_status"] == 200

    db = TestingSession()
    rows = db.query(WebhookDelivery).filter_by(document_id=uuid.UUID(alpha["doc_id"])).all()
    db.close()
    assert len(rows) == 1
    row = rows[0]
    assert row.response_status == 200
    assert row.attempt_count == 1
    assert row.delivered_at is not None
    assert row.url == "https://receiver.test/hook"


def test_send_webhook_task_records_failure_and_increments_attempt(engine, tenant_with_document, monkeypatch):
    from app.core import database as core_db
    from app.workers import tasks as worker_tasks

    alpha, _ = tenant_with_document
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(core_db, "SessionLocal", TestingSession)

    # Pre-seed an attempt so attempt_count should become 2
    _seed_delivery(
        engine, tenant_id=alpha["tenant_id"], document_id=alpha["doc_id"],
        status=502, body="bad gateway", attempt=1, delivered=False,
    )

    # Cap retries to 0 so we observe exactly one new failure row (no recursion).
    monkeypatch.setattr(worker_tasks.send_webhook, "max_retries", 0)

    with patch.object(
        worker_tasks,
        "deliver",
        return_value=DeliveryResult(
            status_code=500, body_excerpt="server crash", ok=False, error=None
        ),
    ):
        result = worker_tasks.send_webhook.apply(
            args=[
                "https://receiver.test/hook",
                {"document_id": alpha["doc_id"]},
                None,
                alpha["doc_id"],
                alpha["tenant_id"],
            ],
            throw=False,
        ).get(disable_sync_subtasks=False)

    assert result["status"] == "failed"
    assert result["http_status"] == 500

    db = TestingSession()
    rows = (
        db.query(WebhookDelivery)
        .filter_by(document_id=uuid.UUID(alpha["doc_id"]))
        .order_by(WebhookDelivery.attempt_count.asc())
        .all()
    )
    db.close()
    assert len(rows) == 2
    assert [r.attempt_count for r in rows] == [1, 2]
    assert rows[1].response_status == 500
    assert rows[1].delivered_at is None
    assert "server crash" in (rows[1].response_body or "")
