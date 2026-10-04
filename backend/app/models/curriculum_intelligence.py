from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CurriculumAlignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_alignments"
    __table_args__ = (
        CheckConstraint(
            "((learning_outcome_id IS NOT NULL) + (competency_id IS NOT NULL)) = 1",
            name="ck_curriculum_alignment_one_target",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_curriculum_alignment_confidence",
        ),
        UniqueConstraint(
            "curriculum_node_id",
            "learning_outcome_id",
            "competency_id",
            "relationship_type",
            "source_revision_id",
            name="uq_curriculum_alignment_evidence",
        ),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    curriculum_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    learning_outcome_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("learning_outcomes.id", ondelete="CASCADE"),
        index=True,
    )
    competency_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("competencies.id", ondelete="CASCADE"),
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    inferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AssessmentEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_evidence"
    __table_args__ = (
        UniqueConstraint(
            "curriculum_version_id",
            "source_revision_id",
            "grade_node_id",
            "subject_node_id",
            "evidence_type",
            "source_locator",
            name="uq_assessment_evidence_binding",
        ),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grade_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    subject_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
