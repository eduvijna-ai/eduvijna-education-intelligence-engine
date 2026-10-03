"""close audited Day 3 Source Intelligence gaps

Revision ID: 20261003_0006
Revises: 20261002_0005
Create Date: 2026-10-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261003_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("institution_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("teacher_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_sources_organization_id_organizations",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_sources_institution_id_institutions",
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_sources_teacher_id_teachers",
            "teachers",
            ["teacher_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_source_institution_same_organization",
            "institutions",
            ["institution_id", "organization_id"],
            ["id", "organization_id"],
        )
        batch.create_foreign_key(
            "fk_source_teacher_same_institution",
            "teachers",
            ["teacher_id", "institution_id"],
            ["id", "institution_id"],
        )
        batch.create_check_constraint(
            "ck_source_institution_requires_organization",
            "institution_id IS NULL OR organization_id IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_source_teacher_requires_institution",
            "teacher_id IS NULL OR institution_id IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_source_ownership_shape",
            "("
            "source_type = 'institution_content' "
            "AND organization_id IS NOT NULL "
            "AND institution_id IS NOT NULL "
            "AND teacher_id IS NULL"
            ") OR ("
            "source_type = 'teacher_content' "
            "AND organization_id IS NOT NULL "
            "AND institution_id IS NOT NULL "
            "AND teacher_id IS NOT NULL"
            ") OR ("
            "source_type NOT IN ('institution_content','teacher_content') "
            "AND organization_id IS NULL "
            "AND institution_id IS NULL "
            "AND teacher_id IS NULL"
            ")",
        )

    op.create_index("ix_sources_organization_id", "sources", ["organization_id"])
    op.create_index("ix_sources_institution_id", "sources", ["institution_id"])
    op.create_index("ix_sources_teacher_id", "sources", ["teacher_id"])

    with op.batch_alter_table("source_revisions") as batch:
        batch.add_column(
            sa.Column("source_snapshot_checksum", sa.String(64), nullable=True)
        )
        batch.add_column(sa.Column("extracted_checksum", sa.String(64), nullable=True))
        batch.add_column(sa.Column("validated_checksum", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("approval_fingerprint", sa.String(64), nullable=True)
        )

    op.execute(
        """
        UPDATE source_revisions
        SET source_snapshot_checksum = checksum,
            extracted_checksum = CASE
                WHEN extraction_status = 'succeeded' THEN checksum
                ELSE NULL
            END,
            validated_checksum = CASE
                WHEN status IN ('validated','approved','active','superseded')
                THEN checksum
                ELSE NULL
            END
        """
    )

    with op.batch_alter_table("source_revisions") as batch:
        batch.alter_column(
            "source_snapshot_checksum",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch.drop_constraint("uq_source_revision_checksum", type_="unique")
        batch.drop_constraint("ck_source_revision_active_slot", type_="check")
        batch.create_unique_constraint(
            "uq_source_revision_identity",
            ["source_id", "checksum", "source_snapshot_checksum"],
        )
        batch.create_check_constraint(
            "ck_source_revision_active_slot",
            "(status = 'active' AND active_slot IS 1) OR "
            "(status <> 'active' AND active_slot IS NULL)",
        )

    op.create_index(
        "ix_source_revisions_source_snapshot_checksum",
        "source_revisions",
        ["source_snapshot_checksum"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_revisions_source_snapshot_checksum",
        table_name="source_revisions",
    )
    with op.batch_alter_table("source_revisions") as batch:
        batch.drop_constraint("ck_source_revision_active_slot", type_="check")
        batch.drop_constraint("uq_source_revision_identity", type_="unique")
        batch.create_unique_constraint(
            "uq_source_revision_checksum",
            ["source_id", "checksum"],
        )
        batch.create_check_constraint(
            "ck_source_revision_active_slot",
            "active_slot IS NULL OR (active_slot = 1 AND status = 'active')",
        )
        batch.drop_column("approval_fingerprint")
        batch.drop_column("validated_checksum")
        batch.drop_column("extracted_checksum")
        batch.drop_column("source_snapshot_checksum")

    op.drop_index("ix_sources_teacher_id", table_name="sources")
    op.drop_index("ix_sources_institution_id", table_name="sources")
    op.drop_index("ix_sources_organization_id", table_name="sources")

    with op.batch_alter_table("sources") as batch:
        batch.drop_constraint("ck_source_ownership_shape", type_="check")
        batch.drop_constraint(
            "ck_source_teacher_requires_institution",
            type_="check",
        )
        batch.drop_constraint(
            "ck_source_institution_requires_organization",
            type_="check",
        )
        batch.drop_constraint(
            "fk_source_teacher_same_institution",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_source_institution_same_organization",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_teacher_id_teachers",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_institution_id_institutions",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_organization_id_organizations",
            type_="foreignkey",
        )
        batch.drop_column("teacher_id")
        batch.drop_column("institution_id")
        batch.drop_column("organization_id")
