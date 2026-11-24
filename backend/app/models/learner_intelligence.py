from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class LearnerProfileVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learner_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "learner_id",
            "profile_version",
            name="uq_learner_profile_version",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    synthetic_harness_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AssessmentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "learner_id",
            "idempotency_key",
            name="uq_attempt_learner_idempotency",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trust_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    exam_pack_code: Mapped[str | None] = mapped_column(String(128))
    exam_version_id: Mapped[str | None] = mapped_column(String(36))
    performance_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="practice")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_marks: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    max_marks: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    synthetic_harness_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class IssuedItemSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "issued_item_snapshots"
    __table_args__ = (
        UniqueConstraint("attempt_id", "item_sequence", name="uq_snapshot_attempt_item"),
    )

    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True
    )
    item_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    marks_if_correct: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    marks_if_incorrect: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    marks_if_blank: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    scoring_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)


class AttemptResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attempt_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "item_sequence", name="uq_response_attempt_item"),
    )

    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True
    )
    item_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    response_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_option_keys_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    numeric_value: Mapped[str | None] = mapped_column(String(64))
    descriptive_text: Mapped[str | None] = mapped_column(Text)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScoreEvidenceEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "score_evidence_events"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "item_sequence",
            "event_kind",
            name="uq_score_event_attempt_item_kind",
        ),
    )

    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    item_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="item_scored")
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    marks_awarded: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    snapshot_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    concept_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ConceptMasteryRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concept_mastery_records"
    __table_args__ = (
        UniqueConstraint(
            "learner_id",
            "concept_code",
            "policy_version",
            name="uq_mastery_learner_concept_policy",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    institution_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    concept_code: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mastery_level: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    support_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    support_incorrect: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_evidence_event_id: Mapped[str | None] = mapped_column(String(36))


class DiagnosticProfileEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_profile_events"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "item_sequence",
            "misconception_code",
            name="uq_diag_attempt_item_misconception",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), index=True)
    response_id: Mapped[str | None] = mapped_column(String(36))
    item_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    option_key: Mapped[str] = mapped_column(String(64), nullable=False)
    misconception_code: Mapped[str] = mapped_column(String(128), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    hypothesis_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class QuestionHistoryObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_history_observations"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "item_sequence",
            "observation_kind",
            name="uq_history_attempt_item_kind",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), index=True)
    question_id: Mapped[str] = mapped_column(String(36), nullable=False)
    item_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(32))
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LearnerMemoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learner_memory_entries"
    __table_args__ = (
        UniqueConstraint("learner_id", "memory_key", "entry_version", name="uq_memory_key_version"),
    )

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    memory_key: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(36))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retracted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FinalizationIdempotencyRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "finalization_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "learner_id",
            "idempotency_key",
            name="uq_finalize_idempotency",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    institution_id: Mapped[str] = mapped_column(String(36), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)