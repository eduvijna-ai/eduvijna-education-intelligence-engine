"""add canonical domain model

Revision ID: 20261001_0002
Revises: 20261001_0001
Create Date: 2026-10-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261001_0002"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def _id() -> sa.Column[str]:
    return sa.Column("id", sa.String(length=36), primary_key=True, nullable=False)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "sources",
        _id(),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("authority", sa.String(255), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("board_or_exam", sa.String(255), nullable=True),
        sa.Column("academic_year", sa.String(64), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("copyright_classification", sa.String(128), nullable=True),
        sa.Column("trust_tier", sa.String(64), nullable=False),
        sa.Column("anythingllm_workspace", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    for name, column in (
        ("ix_sources_country", "country"),
        ("ix_sources_board_or_exam", "board_or_exam"),
        ("ix_sources_academic_year", "academic_year"),
        ("ix_sources_checksum", "checksum"),
        ("ix_sources_status", "status"),
    ):
        op.create_index(name, "sources", [column])

    op.create_table(
        "education_frameworks",
        _id(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_education_framework_code"),
    )
    op.create_index("ix_education_frameworks_code", "education_frameworks", ["code"], unique=True)
    op.create_index("ix_education_frameworks_country", "education_frameworks", ["country"])

    op.create_table(
        "curriculum_packs",
        _id(),
        sa.Column(
            "framework_id",
            sa.String(36),
            sa.ForeignKey("education_frameworks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("authority", sa.String(255), nullable=True),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_curriculum_pack_code"),
    )
    op.create_index("ix_curriculum_packs_code", "curriculum_packs", ["code"], unique=True)
    op.create_index("ix_curriculum_packs_country", "curriculum_packs", ["country"])

    op.create_table(
        "curriculum_versions",
        _id(),
        sa.Column(
            "curriculum_pack_id",
            sa.String(36),
            sa.ForeignKey("curriculum_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_code", sa.String(64), nullable=False),
        sa.Column("academic_year", sa.String(64), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "curriculum_pack_id",
            "version_code",
            name="uq_curriculum_version_code",
        ),
    )
    op.create_index(
        "ix_curriculum_versions_curriculum_pack_id",
        "curriculum_versions",
        ["curriculum_pack_id"],
    )
    op.create_index("ix_curriculum_versions_academic_year", "curriculum_versions", ["academic_year"])
    op.create_index("ix_curriculum_versions_status", "curriculum_versions", ["status"])

    op.create_table(
        "curriculum_nodes",
        _id(),
        sa.Column(
            "curriculum_version_id",
            sa.String(36),
            sa.ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "curriculum_version_id",
            "parent_id",
            "node_type",
            "code",
            name="uq_curriculum_node_scope",
        ),
    )
    op.create_index(
        "ix_curriculum_nodes_curriculum_version_id",
        "curriculum_nodes",
        ["curriculum_version_id"],
    )
    op.create_index("ix_curriculum_nodes_parent_id", "curriculum_nodes", ["parent_id"])
    op.create_index("ix_curriculum_nodes_node_type", "curriculum_nodes", ["node_type"])

    op.create_table(
        "learning_outcomes",
        _id(),
        sa.Column(
            "curriculum_version_id",
            sa.String(36),
            sa.ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "curriculum_version_id",
            "code",
            name="uq_learning_outcome_code",
        ),
    )
    op.create_index(
        "ix_learning_outcomes_curriculum_version_id",
        "learning_outcomes",
        ["curriculum_version_id"],
    )

    op.create_table(
        "competencies",
        _id(),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_competency_code"),
    )
    op.create_index("ix_competencies_code", "competencies", ["code"], unique=True)

    op.create_table(
        "concept_prerequisites",
        _id(),
        sa.Column(
            "prerequisite_concept_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_concept_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "prerequisite_concept_id <> target_concept_id",
            name="ck_concept_prerequisite_not_self",
        ),
        sa.CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)",
            name="ck_prereq_weight",
        ),
        sa.UniqueConstraint(
            "prerequisite_concept_id",
            "target_concept_id",
            name="uq_concept_prerequisite_edge",
        ),
    )
    op.create_index(
        "ix_concept_prerequisites_prerequisite_concept_id",
        "concept_prerequisites",
        ["prerequisite_concept_id"],
    )
    op.create_index(
        "ix_concept_prerequisites_target_concept_id",
        "concept_prerequisites",
        ["target_concept_id"],
    )

    op.create_table(
        "curriculum_version_sources",
        sa.Column(
            "curriculum_version_id",
            sa.String(36),
            sa.ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "curriculum_node_learning_outcomes",
        sa.Column(
            "curriculum_node_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "learning_outcome_id",
            sa.String(36),
            sa.ForeignKey("learning_outcomes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "curriculum_node_competencies",
        sa.Column(
            "curriculum_node_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "competency_id",
            sa.String(36),
            sa.ForeignKey("competencies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "exam_packs",
        _id(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("authority", sa.String(255), nullable=True),
        sa.Column("country", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_exam_pack_code"),
    )
    op.create_index("ix_exam_packs_code", "exam_packs", ["code"], unique=True)
    op.create_index("ix_exam_packs_country", "exam_packs", ["country"])

    op.create_table(
        "exam_versions",
        _id(),
        sa.Column(
            "exam_pack_id",
            sa.String(36),
            sa.ForeignKey("exam_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_code", sa.String(64), nullable=False),
        sa.Column("academic_year", sa.String(64), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("total_marks", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("exam_pack_id", "version_code", name="uq_exam_version_code"),
    )
    op.create_index("ix_exam_versions_exam_pack_id", "exam_versions", ["exam_pack_id"])
    op.create_index("ix_exam_versions_academic_year", "exam_versions", ["academic_year"])
    op.create_index("ix_exam_versions_status", "exam_versions", ["status"])

    op.create_table(
        "exam_sections",
        _id(),
        sa.Column(
            "exam_version_id",
            sa.String(36),
            sa.ForeignKey("exam_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_section_id",
            sa.String(36),
            sa.ForeignKey("exam_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("subject_code", sa.String(128), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "exam_version_id",
            "parent_section_id",
            "code",
            name="uq_exam_section_scope",
        ),
    )
    op.create_index("ix_exam_sections_exam_version_id", "exam_sections", ["exam_version_id"])
    op.create_index("ix_exam_sections_parent_section_id", "exam_sections", ["parent_section_id"])
    op.create_index("ix_exam_sections_subject_code", "exam_sections", ["subject_code"])

    op.create_table(
        "exam_blueprint_rules",
        _id(),
        sa.Column(
            "exam_version_id",
            sa.String(36),
            sa.ForeignKey("exam_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            sa.String(36),
            sa.ForeignKey("exam_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("selector_json", sa.JSON(), nullable=False),
        sa.Column("exact_count", sa.Integer(), nullable=True),
        sa.Column("min_count", sa.Integer(), nullable=True),
        sa.Column("max_count", sa.Integer(), nullable=True),
        sa.Column("marks_per_question", sa.Float(), nullable=True),
        sa.Column("negative_marks", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "exact_count IS NULL OR exact_count >= 0",
            name="ck_rule_exact_nonnegative",
        ),
        sa.CheckConstraint("min_count IS NULL OR min_count >= 0", name="ck_rule_min_nonnegative"),
        sa.CheckConstraint("max_count IS NULL OR max_count >= 0", name="ck_rule_max_nonnegative"),
        sa.CheckConstraint(
            "min_count IS NULL OR max_count IS NULL OR min_count <= max_count",
            name="ck_rule_min_lte_max",
        ),
    )
    op.create_index(
        "ix_exam_blueprint_rules_exam_version_id",
        "exam_blueprint_rules",
        ["exam_version_id"],
    )
    op.create_index("ix_exam_blueprint_rules_section_id", "exam_blueprint_rules", ["section_id"])
    op.create_index("ix_exam_blueprint_rules_rule_type", "exam_blueprint_rules", ["rule_type"])

    op.create_table(
        "exam_version_sources",
        sa.Column(
            "exam_version_id",
            sa.String(36),
            sa.ForeignKey("exam_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "diagnostic_taxonomy_entries",
        _id(),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("diagnostic_taxonomy_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_diagnostic_taxonomy_code"),
    )
    op.create_index(
        "ix_diagnostic_taxonomy_entries_parent_id",
        "diagnostic_taxonomy_entries",
        ["parent_id"],
    )
    op.create_index(
        "ix_diagnostic_taxonomy_entries_code",
        "diagnostic_taxonomy_entries",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_diagnostic_taxonomy_entries_category",
        "diagnostic_taxonomy_entries",
        ["category"],
    )

    op.create_table(
        "questions",
        _id(),
        sa.Column("external_code", sa.String(128), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column(
            "curriculum_version_id",
            sa.String(36),
            sa.ForeignKey("curriculum_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "exam_version_id",
            sa.String(36),
            sa.ForeignKey("exam_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "primary_curriculum_node_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("stem_text", sa.Text(), nullable=False),
        sa.Column("stem_latex", sa.Text(), nullable=True),
        sa.Column("solution_text", sa.Text(), nullable=True),
        sa.Column("solution_latex", sa.Text(), nullable=True),
        sa.Column("answer_json", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("cognitive_level", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "difficulty IS NULL OR (difficulty >= 1 AND difficulty <= 5)",
            name="ck_question_difficulty",
        ),
    )
    for name, column in (
        ("ix_questions_external_code", "external_code"),
        ("ix_questions_curriculum_version_id", "curriculum_version_id"),
        ("ix_questions_exam_version_id", "exam_version_id"),
        ("ix_questions_primary_curriculum_node_id", "primary_curriculum_node_id"),
        ("ix_questions_question_type", "question_type"),
        ("ix_questions_cognitive_level", "cognitive_level"),
        ("ix_questions_status", "status"),
    ):
        op.create_index(name, "questions", [column])

    op.create_table(
        "question_options",
        _id(),
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_key", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("latex", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "diagnostic_taxonomy_entry_id",
            sa.String(36),
            sa.ForeignKey("diagnostic_taxonomy_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("question_id", "option_key", name="uq_question_option_key"),
    )
    op.create_index("ix_question_options_question_id", "question_options", ["question_id"])
    op.create_index(
        "ix_question_options_diagnostic_taxonomy_entry_id",
        "question_options",
        ["diagnostic_taxonomy_entry_id"],
    )
    op.create_index("ix_question_options_error_code", "question_options", ["error_code"])

    op.create_table(
        "question_assets",
        _id(),
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_question_assets_question_id", "question_assets", ["question_id"])
    op.create_index("ix_question_assets_asset_type", "question_assets", ["asset_type"])

    op.create_table(
        "question_competencies",
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "competency_id",
            sa.String(36),
            sa.ForeignKey("competencies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "question_learning_outcomes",
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "learning_outcome_id",
            sa.String(36),
            sa.ForeignKey("learning_outcomes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "question_prerequisites",
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "concept_node_id",
            sa.String(36),
            sa.ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "question_sources",
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "test_definitions",
        _id(),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column(
            "curriculum_version_id",
            sa.String(36),
            sa.ForeignKey("curriculum_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "exam_version_id",
            sa.String(36),
            sa.ForeignKey("exam_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("blueprint_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_test_definition_code"),
    )
    op.create_index("ix_test_definitions_code", "test_definitions", ["code"], unique=True)
    op.create_index(
        "ix_test_definitions_curriculum_version_id",
        "test_definitions",
        ["curriculum_version_id"],
    )
    op.create_index("ix_test_definitions_exam_version_id", "test_definitions", ["exam_version_id"])
    op.create_index("ix_test_definitions_status", "test_definitions", ["status"])

    op.create_table(
        "test_questions",
        _id(),
        sa.Column(
            "test_definition_id",
            sa.String(36),
            sa.ForeignKey("test_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("section_code", sa.String(128), nullable=True),
        sa.Column("marks", sa.Float(), nullable=True),
        sa.Column("negative_marks", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "test_definition_id",
            "sequence",
            name="uq_test_question_sequence",
        ),
        sa.UniqueConstraint(
            "test_definition_id",
            "question_id",
            name="uq_test_question_question",
        ),
    )
    op.create_index("ix_test_questions_test_definition_id", "test_questions", ["test_definition_id"])
    op.create_index("ix_test_questions_question_id", "test_questions", ["question_id"])

    op.create_table(
        "policy_rules",
        _id(),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_code", sa.String(128), nullable=False),
        sa.Column("policy_key", sa.String(255), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_policy_rules_scope_type", "policy_rules", ["scope_type"])
    op.create_index("ix_policy_rules_scope_code", "policy_rules", ["scope_code"])
    op.create_index("ix_policy_rules_policy_key", "policy_rules", ["policy_key"])
    op.create_index("ix_policy_rules_priority", "policy_rules", ["priority"])

    op.create_table(
        "policy_rule_sources",
        sa.Column(
            "policy_rule_id",
            sa.String(36),
            sa.ForeignKey("policy_rules.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    for table in (
        "policy_rule_sources",
        "policy_rules",
        "test_questions",
        "test_definitions",
        "question_sources",
        "question_prerequisites",
        "question_learning_outcomes",
        "question_competencies",
        "question_assets",
        "question_options",
        "questions",
        "diagnostic_taxonomy_entries",
        "exam_version_sources",
        "exam_blueprint_rules",
        "exam_sections",
        "exam_versions",
        "exam_packs",
        "curriculum_node_competencies",
        "curriculum_node_learning_outcomes",
        "curriculum_version_sources",
        "concept_prerequisites",
        "competencies",
        "learning_outcomes",
        "curriculum_nodes",
        "curriculum_versions",
        "curriculum_packs",
        "education_frameworks",
        "sources",
    ):
        op.drop_table(table)
