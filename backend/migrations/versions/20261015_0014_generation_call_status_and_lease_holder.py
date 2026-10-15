"""Day 8 generation call status and lease holder

Revision ID: 20261015_0014
Revises: 20261015_0013
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0014"
down_revision = "20261015_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_generation_calls",
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
    )
    op.alter_column(
        "orchestration_generation_calls",
        "response_json",
        existing_type=sa.JSON(),
        nullable=True,
    )
    op.add_column(
        "orchestration_checkpoint_leases",
        sa.Column("holder_id", sa.String(64), nullable=True),
    )
    op.alter_column("orchestration_generation_calls", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("orchestration_checkpoint_leases", "holder_id")
    op.alter_column(
        "orchestration_generation_calls",
        "response_json",
        existing_type=sa.JSON(),
        nullable=False,
    )
    op.drop_column("orchestration_generation_calls", "status")
