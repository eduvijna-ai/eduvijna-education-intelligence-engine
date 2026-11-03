"""Day 10 R24 curator credential scope and durable approval lineage

Revision ID: 20261103_0016
Revises: 20261102_0015
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261103_0016"
down_revision = "20261102_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curator_operator_credentials",
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "curator_operator_credentials",
        sa.Column("board_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "curator_operator_credentials",
        sa.Column("board_scope_authorized", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_table(
        "curator_durable_approval_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_jti", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=128), nullable=False),
        sa.Column("admin_actor_id", sa.String(length=36), nullable=False),
        sa.Column("source_audit_event_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at_iso", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_jti", name="uq_curator_durable_decision_jti"),
    )
    op.create_index(
        op.f("ix_curator_durable_approval_records_claim_id"),
        "curator_durable_approval_records",
        ["claim_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_curator_durable_approval_records_claim_id"),
        table_name="curator_durable_approval_records",
    )
    op.drop_table("curator_durable_approval_records")
    op.drop_column("curator_operator_credentials", "board_scope_authorized")
    op.drop_column("curator_operator_credentials", "board_code")
    op.drop_column("curator_operator_credentials", "curriculum_version_id")
