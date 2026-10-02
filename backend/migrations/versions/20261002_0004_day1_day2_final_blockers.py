"""close remaining Day 1 and Day 2 integrity blockers

Revision ID: 20261002_0004
Revises: 20261001_0003
Create Date: 2026-10-02
"""
from __future__ import annotations

from alembic import op

revision = "20261002_0004"
down_revision = "20261001_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("institutions") as batch:
        batch.create_unique_constraint(
            "uq_institution_id_org",
            ["id", "organization_id"],
        )

    with op.batch_alter_table("teachers") as batch:
        batch.create_unique_constraint(
            "uq_teacher_id_institution",
            ["id", "institution_id"],
        )

    with op.batch_alter_table("learners") as batch:
        batch.create_foreign_key(
            "fk_learner_teacher_same_institution",
            "teachers",
            ["primary_teacher_id", "institution_id"],
            ["id", "institution_id"],
        )

    with op.batch_alter_table("admin_actors") as batch:
        batch.create_check_constraint(
            "ck_admin_institution_requires_organization",
            "institution_id IS NULL OR organization_id IS NOT NULL",
        )
        batch.create_foreign_key(
            "fk_admin_institution_same_organization",
            "institutions",
            ["institution_id", "organization_id"],
            ["id", "organization_id"],
        )

    with op.batch_alter_table("api_clients") as batch:
        batch.create_foreign_key(
            "fk_api_client_institution_same_organization",
            "institutions",
            ["institution_id", "organization_id"],
            ["id", "organization_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("api_clients") as batch:
        batch.drop_constraint(
            "fk_api_client_institution_same_organization",
            type_="foreignkey",
        )

    with op.batch_alter_table("admin_actors") as batch:
        batch.drop_constraint(
            "fk_admin_institution_same_organization",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "ck_admin_institution_requires_organization",
            type_="check",
        )

    with op.batch_alter_table("learners") as batch:
        batch.drop_constraint(
            "fk_learner_teacher_same_institution",
            type_="foreignkey",
        )

    with op.batch_alter_table("teachers") as batch:
        batch.drop_constraint(
            "uq_teacher_id_institution",
            type_="unique",
        )

    with op.batch_alter_table("institutions") as batch:
        batch.drop_constraint(
            "uq_institution_id_org",
            type_="unique",
        )
