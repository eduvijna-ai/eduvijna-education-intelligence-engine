"""Add bootstrap audit table for R24

Revision ID: 20261103_0017
Revises: 20261103_0016
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261103_0017"
down_revision = "20261103_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curator_bootstrap_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("admin_actor_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_curator_bootstrap_audit_events_admin_actor_id"),
        "curator_bootstrap_audit_events",
        ["admin_actor_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_curator_bootstrap_audit_events_admin_actor_id"),
        table_name="curator_bootstrap_audit_events",
    )
    op.drop_table("curator_bootstrap_audit_events")
