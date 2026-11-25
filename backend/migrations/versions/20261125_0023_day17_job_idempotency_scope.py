"""Day17 scoped job idempotency key

Revision ID: 20261125_0023
Revises: 20261124_0022
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261125_0023"
down_revision = "20261124_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("durable_async_jobs") as batch:
        batch.add_column(
            sa.Column("idempotency_scope_key", sa.String(length=128), nullable=True)
        )
    op.execute(
        "UPDATE durable_async_jobs SET idempotency_scope_key = "
        "lower(hex(randomblob(16))) WHERE idempotency_scope_key IS NULL"
    )
    with op.batch_alter_table("durable_async_jobs") as batch:
        batch.alter_column("idempotency_scope_key", nullable=False)
        batch.drop_constraint("uq_job_org_idempotency", type_="unique")
        batch.create_index("ix_durable_async_jobs_idempotency_scope_key", ["idempotency_scope_key"])
        batch.create_unique_constraint(
            "uq_job_idempotency_scope",
            ["organization_id", "idempotency_scope_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("durable_async_jobs") as batch:
        batch.drop_constraint("uq_job_idempotency_scope", type_="unique")
        batch.drop_index("ix_durable_async_jobs_idempotency_scope_key")
        batch.create_unique_constraint(
            "uq_job_org_idempotency",
            ["organization_id", "idempotency_key"],
        )
        batch.drop_column("idempotency_scope_key")