"""Curator auth indexes aligned with SQLAlchemy models (alembic check parity)

Revision ID: 20261109_0018
Revises: 20261103_0017
Create Date: 2026-11-09
"""

from __future__ import annotations

from alembic import op

revision = "20261109_0018"
down_revision = "20261103_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_curator_durable_approval_records_decision_jti"),
        "curator_durable_approval_records",
        ["decision_jti"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_durable_approval_records_admin_actor_id"),
        "curator_durable_approval_records",
        ["admin_actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_organization_id"),
        "curator_operator_credentials",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_institution_id"),
        "curator_operator_credentials",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_teacher_id"),
        "curator_operator_credentials",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_curriculum_version_id"),
        "curator_operator_credentials",
        ["curriculum_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curator_operator_credentials_board_code"),
        "curator_operator_credentials",
        ["board_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_curator_operator_credentials_board_code"),
        table_name="curator_operator_credentials",
    )
    op.drop_index(
        op.f("ix_curator_operator_credentials_curriculum_version_id"),
        table_name="curator_operator_credentials",
    )
    op.drop_index(
        op.f("ix_curator_operator_credentials_teacher_id"),
        table_name="curator_operator_credentials",
    )
    op.drop_index(
        op.f("ix_curator_operator_credentials_institution_id"),
        table_name="curator_operator_credentials",
    )
    op.drop_index(
        op.f("ix_curator_operator_credentials_organization_id"),
        table_name="curator_operator_credentials",
    )
    op.drop_index(
        op.f("ix_curator_durable_approval_records_admin_actor_id"),
        table_name="curator_durable_approval_records",
    )
    op.drop_index(
        op.f("ix_curator_durable_approval_records_decision_jti"),
        table_name="curator_durable_approval_records",
    )
