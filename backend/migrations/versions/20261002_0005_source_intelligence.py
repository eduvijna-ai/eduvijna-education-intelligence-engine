"""add Source Intelligence registry and revision lifecycle

Revision ID: 20261002_0005
Revises: 20261002_0004
Create Date: 2026-10-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261002_0005"
down_revision = "20261002_0004"
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
        "source_revisions",
        _id(),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("ingestion_method", sa.String(32), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_status", sa.String(32), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anythingllm_document_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "source_id",
            "revision_number",
            name="uq_source_revision_number",
        ),
        sa.UniqueConstraint(
            "source_id",
            "checksum",
            name="uq_source_revision_checksum",
        ),
        sa.UniqueConstraint(
            "source_id",
            "active_slot",
            name="uq_source_single_active_revision",
        ),
        sa.CheckConstraint(
            "active_slot IS NULL OR (active_slot = 1 AND status = 'active')",
            name="ck_source_revision_active_slot",
        ),
    )
    for name, column in (
        ("ix_source_revisions_source_id", "source_id"),
        ("ix_source_revisions_ingestion_method", "ingestion_method"),
        ("ix_source_revisions_checksum", "checksum"),
        ("ix_source_revisions_extraction_status", "extraction_status"),
        ("ix_source_revisions_status", "status"),
    ):
        op.create_index(name, "source_revisions", [column])

    op.create_table(
        "source_diffs",
        _id(),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_revision_id",
            sa.String(36),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "to_revision_id",
            sa.String(36),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checksum_changed", sa.Boolean(), nullable=False),
        sa.Column("metadata_changes_json", sa.JSON(), nullable=False),
        sa.Column("content_diff_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "from_revision_id",
            "to_revision_id",
            name="uq_source_diff_revision_pair",
        ),
    )
    op.create_index("ix_source_diffs_source_id", "source_diffs", ["source_id"])
    op.create_index(
        "ix_source_diffs_from_revision_id",
        "source_diffs",
        ["from_revision_id"],
    )
    op.create_index(
        "ix_source_diffs_to_revision_id",
        "source_diffs",
        ["to_revision_id"],
    )

    op.create_table(
        "source_audit_events",
        _id(),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_revision_id",
            sa.String(36),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    for name, column in (
        ("ix_source_audit_events_source_id", "source_id"),
        ("ix_source_audit_events_source_revision_id", "source_revision_id"),
        ("ix_source_audit_events_event_type", "event_type"),
        ("ix_source_audit_events_actor_id", "actor_id"),
        ("ix_source_audit_events_request_id", "request_id"),
    ):
        op.create_index(name, "source_audit_events", [column])

    for table_name, entity_table, entity_column in (
        (
            "curriculum_version_source_revisions",
            "curriculum_versions",
            "curriculum_version_id",
        ),
        ("exam_version_source_revisions", "exam_versions", "exam_version_id"),
        ("question_source_revisions", "questions", "question_id"),
        ("policy_rule_source_revisions", "policy_rules", "policy_rule_id"),
    ):
        op.create_table(
            table_name,
            sa.Column(
                entity_column,
                sa.String(36),
                sa.ForeignKey(f"{entity_table}.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "source_revision_id",
                sa.String(36),
                sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )


def downgrade() -> None:
    for table_name in (
        "policy_rule_source_revisions",
        "question_source_revisions",
        "exam_version_source_revisions",
        "curriculum_version_source_revisions",
    ):
        op.drop_table(table_name)

    for name in (
        "ix_source_audit_events_request_id",
        "ix_source_audit_events_actor_id",
        "ix_source_audit_events_event_type",
        "ix_source_audit_events_source_revision_id",
        "ix_source_audit_events_source_id",
    ):
        op.drop_index(name, table_name="source_audit_events")
    op.drop_table("source_audit_events")

    for name in (
        "ix_source_diffs_to_revision_id",
        "ix_source_diffs_from_revision_id",
        "ix_source_diffs_source_id",
    ):
        op.drop_index(name, table_name="source_diffs")
    op.drop_table("source_diffs")

    for name in (
        "ix_source_revisions_status",
        "ix_source_revisions_extraction_status",
        "ix_source_revisions_checksum",
        "ix_source_revisions_ingestion_method",
        "ix_source_revisions_source_id",
    ):
        op.drop_index(name, table_name="source_revisions")
    op.drop_table("source_revisions")
