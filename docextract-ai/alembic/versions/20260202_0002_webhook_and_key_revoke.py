"""add webhook_secret and api_key revoked_at

Revision ID: 0002_webhook_and_key_revoke
Revises: 0001_initial
Create Date: 2026-02-02 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_webhook_and_key_revoke"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("webhook_secret", sa.String(255), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "revoked_at")
    op.drop_column("tenants", "webhook_secret")
