"""add webhook_deliveries table

Revision ID: 0003_webhook_deliveries
Revises: 0002_webhook_and_key_revoke
Create Date: 2026-02-03 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_webhook_deliveries"
down_revision = "0002_webhook_and_key_revoke"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_deliveries_doc", "webhook_deliveries", ["document_id"])
    op.create_index(
        "ix_webhook_deliveries_tenant_created",
        "webhook_deliveries",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_tenant_created", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_doc", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
