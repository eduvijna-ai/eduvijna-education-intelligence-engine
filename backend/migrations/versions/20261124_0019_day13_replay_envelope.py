"""Day13 durable replay idempotency envelope (D13-31A)

Revision ID: 20261124_0019
Revises: 20261109_0018
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261124_0019"
down_revision = "20261109_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "d13_replay_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("institution_id", sa.String(64), nullable=False),
        sa.Column("exam_pack_code", sa.String(64), nullable=False),
        sa.Column("exam_version_id", sa.String(36), nullable=False),
        sa.Column("academic_year", sa.String(16), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("reservation_state", sa.String(32), nullable=False),
        sa.Column("owner_token", sa.String(64), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column("result_snapshot_version", sa.String(32), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "institution_id",
            "exam_pack_code",
            "exam_version_id",
            "academic_year",
            "idempotency_key_hash",
            name="uq_d13_replay_reservation_scope_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("d13_replay_reservations")