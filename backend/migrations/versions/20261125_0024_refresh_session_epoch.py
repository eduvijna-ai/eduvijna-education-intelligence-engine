"""Day17 refresh session epoch binding

Revision ID: 20261125_0024
Revises: 20261125_0023
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261125_0024"
down_revision = "20261125_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_refresh_sessions") as batch:
        batch.add_column(sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("application_refresh_sessions") as batch:
        batch.drop_column("session_epoch")