"""Day 8 durable generation call cache

Revision ID: 20261015_0013
Revises: 20261015_0012
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0013"
down_revision = "20261015_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_generation_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "cache_key",
            name="uq_orchestration_generation_call_run_key",
        ),
    )
    op.create_index(
        "ix_orchestration_generation_calls_run_id",
        "orchestration_generation_calls",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orchestration_generation_calls_run_id",
        table_name="orchestration_generation_calls",
    )
    op.drop_table("orchestration_generation_calls")
