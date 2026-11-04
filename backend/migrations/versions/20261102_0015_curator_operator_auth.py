"""Day 10 curator operator credentials and decision nonces

Revision ID: 20261102_0015
Revises: 20261015_0014
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261102_0015"
down_revision = "20261015_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curator_operator_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_actor_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("teacher_id", sa.String(length=36), nullable=True),
        sa.Column("credential_hash_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_actor_id"], ["admin_actors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("admin_actor_id", "role", name="uq_curator_credential_actor_role"),
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_admin_actor_id"),
        "curator_operator_credentials",
        ["admin_actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_role"),
        "curator_operator_credentials",
        ["role"],
        unique=False,
    )
    op.create_table(
        "curator_decision_nonces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at_iso", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti", name="uq_curator_decision_jti"),
    )
    op.create_index(
        op.f("ix_curator_decision_nonces_jti"),
        "curator_decision_nonces",
        ["jti"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_curator_decision_nonces_jti"), table_name="curator_decision_nonces")
    op.drop_table("curator_decision_nonces")
    op.drop_index(
        op.f("ix_curator_operator_credentials_role"), table_name="curator_operator_credentials"
    )
    op.drop_index(
        op.f("ix_curator_operator_credentials_admin_actor_id"),
        table_name="curator_operator_credentials",
    )
    op.drop_table("curator_operator_credentials")
