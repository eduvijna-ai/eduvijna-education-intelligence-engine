"""D13 replay reservation integrity check constraints

Revision ID: 20261124_0020
Revises: 20261124_0019
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261124_0020"
down_revision = "20261124_0019"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("d13_replay_reservations") as batch:
        batch.create_check_constraint(
            "ck_d13_replay_fp_sha256",
            "length(request_fingerprint) = 64",
        )
        batch.create_check_constraint(
            "ck_d13_replay_key_hash_sha256",
            "length(idempotency_key_hash) = 64",
        )
        batch.create_check_constraint(
            "ck_d13_replay_state_valid",
            "reservation_state in ('reserved', 'in_progress', 'replayed')",
        )
        batch.create_check_constraint(
            "ck_d13_replay_pending_no_payload",
            "reservation_state not in ('reserved', 'in_progress') "
            "OR (result_json IS NULL AND payload_sha256 IS NULL "
            "AND result_snapshot_version IS NULL)",
        )
        batch.create_check_constraint(
            "ck_d13_replay_replayed_requires_payload",
            "reservation_state != 'replayed' "
            "OR (owner_token IS NULL AND payload_sha256 IS NOT NULL "
            "AND result_json IS NOT NULL AND result_snapshot_version IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("d13_replay_reservations") as batch:
        batch.drop_constraint("ck_d13_replay_replayed_requires_payload", type_="check")
        batch.drop_constraint("ck_d13_replay_pending_no_payload", type_="check")
        batch.drop_constraint("ck_d13_replay_state_valid", type_="check")
        batch.drop_constraint("ck_d13_replay_key_hash_sha256", type_="check")
        batch.drop_constraint("ck_d13_replay_fp_sha256", type_="check")