"""Day 15 learner intelligence persistence

Revision ID: 20261124_0022
Revises: 20261124_0021
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261124_0022"
down_revision = "20261124_0021"
branch_labels = None
depends_on = None


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "learner_profile_versions",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("mastery_policy_version", sa.String(64), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("synthetic_harness_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("learner_id", "profile_version", name="uq_learner_profile_version"),
    )
    op.create_index("ix_learner_profile_versions_organization_id", "learner_profile_versions", ["organization_id"])
    op.create_index("ix_learner_profile_versions_learner_id", "learner_profile_versions", ["learner_id"])

    op.create_table(
        "assessment_attempts",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("trust_mode", sa.String(64), nullable=False),
        sa.Column("assessment_key", sa.String(128), nullable=False),
        sa.Column("exam_pack_code", sa.String(128)),
        sa.Column("exam_version_id", sa.String(36)),
        sa.Column("performance_mode", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("total_marks", sa.Numeric(12, 4)),
        sa.Column("max_marks", sa.Numeric(12, 4)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("synthetic_harness_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "organization_id", "learner_id", "idempotency_key", name="uq_attempt_learner_idempotency"
        ),
    )
    op.create_index("ix_assessment_attempts_organization_id", "assessment_attempts", ["organization_id"])
    op.create_index("ix_assessment_attempts_learner_id", "assessment_attempts", ["learner_id"])
    op.create_index("ix_assessment_attempts_state", "assessment_attempts", ["state"])

    op.create_table(
        "issued_item_snapshots",
        *_ts_cols(),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_sequence", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(36), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("marks_if_correct", sa.Numeric(12, 4), nullable=False),
        sa.Column("marks_if_incorrect", sa.Numeric(12, 4), nullable=False),
        sa.Column("marks_if_blank", sa.Numeric(12, 4), nullable=False),
        sa.Column("scoring_policy_version", sa.String(64), nullable=False),
        sa.UniqueConstraint("attempt_id", "item_sequence", name="uq_snapshot_attempt_item"),
    )
    op.create_index("ix_issued_item_snapshots_attempt_id", "issued_item_snapshots", ["attempt_id"])

    op.create_table(
        "attempt_responses",
        *_ts_cols(),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_sequence", sa.Integer(), nullable=False),
        sa.Column("response_kind", sa.String(32), nullable=False),
        sa.Column("selected_option_keys_json", sa.JSON(), nullable=False),
        sa.Column("numeric_value", sa.String(64)),
        sa.Column("descriptive_text", sa.Text()),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("attempt_id", "item_sequence", name="uq_response_attempt_item"),
    )
    op.create_index("ix_attempt_responses_attempt_id", "attempt_responses", ["attempt_id"])

    op.create_index("ix_assessment_attempts_institution_id", "assessment_attempts", ["institution_id"])

    op.create_table(
        "score_evidence_events",
        *_ts_cols(),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_sequence", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("marks_awarded", sa.Numeric(12, 4), nullable=False),
        sa.Column("max_marks", sa.Numeric(12, 4), nullable=False),
        sa.Column("snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("concept_codes_json", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "attempt_id", "item_sequence", "event_kind", name="uq_score_event_attempt_item_kind"
        ),
    )

    op.create_index("ix_score_events_learner_id", "score_evidence_events", ["learner_id"])

    op.create_table(
        "concept_mastery_records",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_code", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("mastery_level", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("support_correct", sa.Integer(), nullable=False),
        sa.Column("support_incorrect", sa.Integer(), nullable=False),
        sa.Column("last_evidence_event_id", sa.String(36)),
        sa.UniqueConstraint(
            "learner_id", "concept_code", "policy_version", name="uq_mastery_learner_concept_policy"
        ),
    )

    op.create_index("ix_mastery_learner_id", "concept_mastery_records", ["learner_id"])

    op.create_table(
        "diagnostic_profile_events",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("response_id", sa.String(36)),
        sa.Column("item_sequence", sa.Integer(), nullable=False),
        sa.Column("option_key", sa.String(64), nullable=False),
        sa.Column("misconception_code", sa.String(128), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32)),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("hypothesis_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "attempt_id", "item_sequence", "misconception_code", name="uq_diag_attempt_item_misconception"
        ),
    )

    op.create_table(
        "question_history_observations",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("learner_id", sa.String(36), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(36), nullable=False),
        sa.Column("item_sequence", sa.Integer(), nullable=False),
        sa.Column("observation_kind", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32)),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "attempt_id", "item_sequence", "observation_kind", name="uq_history_attempt_item_kind"
        ),
    )

    op.create_table(
        "learner_memory_entries",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("learner_id", sa.String(36), nullable=False),
        sa.Column("memory_key", sa.String(128), nullable=False),
        sa.Column("entry_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("source_event_id", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("retracted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("learner_id", "memory_key", "entry_version", name="uq_memory_key_version"),
    )

    op.create_table(
        "finalization_idempotency_records",
        *_ts_cols(),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("institution_id", sa.String(36), nullable=False),
        sa.Column("learner_id", sa.String(36), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("content_binding_fingerprint", sa.String(64), nullable=False),
        sa.Column("outcome_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "learner_id", "idempotency_key", name="uq_finalize_idempotency"
        ),
    )


def downgrade() -> None:
    op.drop_table("finalization_idempotency_records")
    op.drop_table("learner_memory_entries")
    op.drop_table("question_history_observations")
    op.drop_table("diagnostic_profile_events")
    op.drop_table("concept_mastery_records")
    op.drop_table("score_evidence_events")
    op.drop_table("attempt_responses")
    op.drop_table("issued_item_snapshots")
    op.drop_table("assessment_attempts")
    op.drop_table("learner_profile_versions")