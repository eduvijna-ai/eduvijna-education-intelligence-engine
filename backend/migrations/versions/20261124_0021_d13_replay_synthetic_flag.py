"""D13 replay synthetic_test_only column for CAS guards

Revision ID: 20261124_0021
Revises: 20261124_0020
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.c01_constraints import D13_SYNTHETIC_TEST_ONLY_CHECK
from migrations.c01_d13_synthetic_preflight import (
    assert_0021_preflight,
    assert_all_rows_synthetic_true,
)

revision = "20261124_0021"
down_revision = "20261124_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    assert_0021_preflight(connection)

    with op.batch_alter_table("d13_replay_reservations") as batch:
        batch.add_column(
            sa.Column("synthetic_test_only", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    dialect = connection.dialect.name
    if dialect == "postgresql":
        op.execute("UPDATE d13_replay_reservations SET synthetic_test_only = true")
    else:
        op.execute("UPDATE d13_replay_reservations SET synthetic_test_only = 1")

    assert_all_rows_synthetic_true(connection)

    with op.batch_alter_table("d13_replay_reservations") as batch:
        batch.create_check_constraint(
            "ck_d13_replay_synthetic_marker",
            D13_SYNTHETIC_TEST_ONLY_CHECK,
        )


def downgrade() -> None:
    with op.batch_alter_table("d13_replay_reservations") as batch:
        batch.drop_constraint("ck_d13_replay_synthetic_marker", type_="check")
        batch.drop_column("synthetic_test_only")