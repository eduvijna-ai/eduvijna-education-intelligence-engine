"""Day 7 knowledge intelligence bindings and audit

Revision ID: 20261012_0011
Revises: 20261007_0010
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261012_0011"
down_revision = "20261007_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ki_source_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_revision_id",
            sa.String(36),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_revision_checksum", sa.String(128), nullable=False),
        sa.Column("anythingllm_workspace", sa.String(255), nullable=False),
        sa.Column("anythingllm_document_id", sa.String(255), nullable=True),
        sa.Column("ownership_scope", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("institution_id", sa.String(36), nullable=True),
        sa.Column("teacher_id", sa.String(36), nullable=True),
        sa.Column("index_status", sa.String(32), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieval_profile_version", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "source_revision_id",
            "retrieval_profile_version",
            name="uq_ki_binding_revision_profile",
        ),
        sa.CheckConstraint(
            "(index_status = 'active' AND retired_at IS NULL) OR (index_status <> 'active')",
            name="ck_ki_binding_active_not_retired",
        ),
    )
    op.create_index("ix_ki_source_bindings_source_id", "ki_source_bindings", ["source_id"])
    op.create_index(
        "ix_ki_source_bindings_source_revision_id", "ki_source_bindings", ["source_revision_id"]
    )
    op.create_index("ix_ki_source_bindings_ownership_scope", "ki_source_bindings", ["ownership_scope"])
    op.create_index("ix_ki_source_bindings_index_status", "ki_source_bindings", ["index_status"])
    op.create_index("ix_ki_binding_source_active", "ki_source_bindings", ["source_id", "index_status"])

    op.create_table(
        "ki_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("query_id", sa.String(64), nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("institution_id", sa.String(36), nullable=True),
        sa.Column("teacher_id", sa.String(36), nullable=True),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("retrieval_profile_version", sa.String(64), nullable=True),
        sa.Column("workspaces_queried_json", sa.JSON(), nullable=False),
        sa.Column("source_revision_ids_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ki_audit_events_event_type", "ki_audit_events", ["event_type"])
    op.create_index("ix_ki_audit_events_query_id", "ki_audit_events", ["query_id"])
    op.create_index("ix_ki_audit_events_query_hash", "ki_audit_events", ["query_hash"])
    op.create_index("ix_ki_audit_events_organization_id", "ki_audit_events", ["organization_id"])
    op.create_index("ix_ki_audit_events_institution_id", "ki_audit_events", ["institution_id"])
    op.create_index("ix_ki_audit_events_teacher_id", "ki_audit_events", ["teacher_id"])
    op.create_index("ix_ki_audit_events_actor_id", "ki_audit_events", ["actor_id"])
    op.create_index(
        "ix_ki_audit_events_retrieval_profile_version",
        "ki_audit_events",
        ["retrieval_profile_version"],
    )
    op.create_index("ix_ki_source_bindings_organization_id", "ki_source_bindings", ["organization_id"])
    op.create_index("ix_ki_source_bindings_institution_id", "ki_source_bindings", ["institution_id"])
    op.create_index("ix_ki_source_bindings_teacher_id", "ki_source_bindings", ["teacher_id"])


def downgrade() -> None:
    op.drop_table("ki_audit_events")
    op.drop_table("ki_source_bindings")
