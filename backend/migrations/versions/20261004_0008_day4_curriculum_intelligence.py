"""add Day 4 curriculum intelligence

Revision ID: 20261004_0008
Revises: 20261003_0007
Create Date: 2026-10-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261004_0008"
down_revision = "20261003_0007"
branch_labels = None
depends_on = None


def _add_source_binding(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column("source_revision_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("source_locator", sa.String(1024), nullable=True))
        batch.create_foreign_key(
            f"fk_{table_name}_source_revision",
            "source_revisions",
            ["source_revision_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            f"ix_{table_name}_source_revision_id",
            ["source_revision_id"],
            unique=False,
        )


def _drop_source_binding(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.drop_index(f"ix_{table_name}_source_revision_id")
        batch.drop_constraint(
            f"fk_{table_name}_source_revision",
            type_="foreignkey",
        )
        batch.drop_column("source_locator")
        batch.drop_column("source_revision_id")


def upgrade() -> None:
    with op.batch_alter_table("education_frameworks") as batch:
        batch.add_column(sa.Column("authority", sa.String(255), nullable=True))
        batch.add_column(sa.Column("version_code", sa.String(64), nullable=True))
        batch.create_index(
            "ix_education_frameworks_version_code",
            ["version_code"],
            unique=False,
        )
    _add_source_binding("education_frameworks")
    _add_source_binding("curriculum_packs")
    _add_source_binding("curriculum_versions")

    with op.batch_alter_table("curriculum_nodes") as batch:
        batch.add_column(sa.Column("official_text", sa.Text(), nullable=True))
    _add_source_binding("curriculum_nodes")

    with op.batch_alter_table("learning_outcomes") as batch:
        batch.add_column(sa.Column("normalized_text", sa.Text(), nullable=True))
    _add_source_binding("learning_outcomes")

    with op.batch_alter_table("competencies") as batch:
        batch.add_column(sa.Column("framework_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("official_text", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_competencies_framework",
            "education_frameworks",
            ["framework_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_competencies_framework_id",
            ["framework_id"],
            unique=False,
        )
    _add_source_binding("competencies")

    op.create_table(
        "curriculum_alignments",
        sa.Column("curriculum_version_id", sa.String(36), nullable=False),
        sa.Column("curriculum_node_id", sa.String(36), nullable=False),
        sa.Column("learning_outcome_id", sa.String(36), nullable=True),
        sa.Column("competency_id", sa.String(36), nullable=True),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_revision_id", sa.String(36), nullable=False),
        sa.Column("source_locator", sa.String(1024), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "((learning_outcome_id IS NOT NULL) + (competency_id IS NOT NULL)) = 1",
            name="ck_curriculum_alignment_one_target",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_curriculum_alignment_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_node_id"],
            ["curriculum_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"],
            ["curriculum_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_outcome_id"],
            ["learning_outcomes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "curriculum_node_id",
            "learning_outcome_id",
            "competency_id",
            "relationship_type",
            "source_revision_id",
            name="uq_curriculum_alignment_evidence",
        ),
    )
    op.create_index(
        "ix_curriculum_alignments_curriculum_version_id",
        "curriculum_alignments",
        ["curriculum_version_id"],
    )
    op.create_index(
        "ix_curriculum_alignments_curriculum_node_id",
        "curriculum_alignments",
        ["curriculum_node_id"],
    )
    op.create_index(
        "ix_curriculum_alignments_learning_outcome_id",
        "curriculum_alignments",
        ["learning_outcome_id"],
    )
    op.create_index(
        "ix_curriculum_alignments_competency_id",
        "curriculum_alignments",
        ["competency_id"],
    )
    op.create_index(
        "ix_curriculum_alignments_status",
        "curriculum_alignments",
        ["status"],
    )
    op.create_index(
        "ix_curriculum_alignments_source_revision_id",
        "curriculum_alignments",
        ["source_revision_id"],
    )

    op.create_table(
        "assessment_evidence",
        sa.Column("curriculum_version_id", sa.String(36), nullable=False),
        sa.Column("grade_node_id", sa.String(36), nullable=True),
        sa.Column("subject_node_id", sa.String(36), nullable=True),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("source_revision_id", sa.String(36), nullable=False),
        sa.Column("source_locator", sa.String(1024), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"],
            ["curriculum_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grade_node_id"],
            ["curriculum_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_node_id"],
            ["curriculum_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "curriculum_version_id",
            "source_revision_id",
            "grade_node_id",
            "subject_node_id",
            "evidence_type",
            "source_locator",
            name="uq_assessment_evidence_binding",
        ),
    )
    op.create_index(
        "ix_assessment_evidence_curriculum_version_id",
        "assessment_evidence",
        ["curriculum_version_id"],
    )
    op.create_index(
        "ix_assessment_evidence_grade_node_id",
        "assessment_evidence",
        ["grade_node_id"],
    )
    op.create_index(
        "ix_assessment_evidence_subject_node_id",
        "assessment_evidence",
        ["subject_node_id"],
    )
    op.create_index(
        "ix_assessment_evidence_evidence_type",
        "assessment_evidence",
        ["evidence_type"],
    )
    op.create_index(
        "ix_assessment_evidence_source_revision_id",
        "assessment_evidence",
        ["source_revision_id"],
    )


def downgrade() -> None:
    op.drop_table("assessment_evidence")
    op.drop_table("curriculum_alignments")

    _drop_source_binding("competencies")
    with op.batch_alter_table("competencies") as batch:
        batch.drop_index("ix_competencies_framework_id")
        batch.drop_constraint("fk_competencies_framework", type_="foreignkey")
        batch.drop_column("official_text")
        batch.drop_column("framework_id")

    _drop_source_binding("learning_outcomes")
    with op.batch_alter_table("learning_outcomes") as batch:
        batch.drop_column("normalized_text")

    _drop_source_binding("curriculum_nodes")
    with op.batch_alter_table("curriculum_nodes") as batch:
        batch.drop_column("official_text")

    _drop_source_binding("curriculum_versions")
    _drop_source_binding("curriculum_packs")
    _drop_source_binding("education_frameworks")
    with op.batch_alter_table("education_frameworks") as batch:
        batch.drop_index("ix_education_frameworks_version_code")
        batch.drop_column("version_code")
        batch.drop_column("authority")
