"""Day 8 orchestration audit and idempotency

Revision ID: 20261015_0012
Revises: 20261012_0011
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0012"
down_revision = "20261012_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("node_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("source_revision_ids_json", sa.JSON(), nullable=False),
        sa.Column("issue_codes_json", sa.JSON(), nullable=False),
        sa.Column("gateway_request_id", sa.String(128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_orchestration_audit_events_run_id", "orchestration_audit_events", ["run_id"]
    )

    op.create_table(
        "orchestration_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_orchestration_idempotency_key"),
    )

    op.create_table(
        "orchestration_checkpoint_leases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False, unique=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orchestration_checkpoint_leases")
    op.drop_table("orchestration_idempotency")
    op.drop_index("ix_orchestration_audit_events_run_id", table_name="orchestration_audit_events")
    op.drop_table("orchestration_audit_events")
