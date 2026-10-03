from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    SourceExtractionStatus,
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceStatus,
    SourceTrustTier,
    SourceType,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.curriculum import CurriculumVersion
    from app.models.examination import ExamVersion
    from app.models.policy import PolicyRule
    from app.models.question import Question


curriculum_version_source_revisions = Table(
    "curriculum_version_source_revisions",
    Base.metadata,
    Column(
        "curriculum_version_id",
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_revision_id",
        String(36),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

exam_version_source_revisions = Table(
    "exam_version_source_revisions",
    Base.metadata,
    Column(
        "exam_version_id",
        String(36),
        ForeignKey("exam_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_revision_id",
        String(36),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

question_source_revisions = Table(
    "question_source_revisions",
    Base.metadata,
    Column(
        "question_id",
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_revision_id",
        String(36),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

policy_rule_source_revisions = Table(
    "policy_rule_source_revisions",
    Base.metadata,
    Column(
        "policy_rule_id",
        String(36),
        ForeignKey("policy_rules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_revision_id",
        String(36),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "institution_id IS NULL OR organization_id IS NOT NULL",
            name="ck_source_institution_requires_organization",
        ),
        CheckConstraint(
            "teacher_id IS NULL OR institution_id IS NOT NULL",
            name="ck_source_teacher_requires_institution",
        ),
        ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_source_institution_same_organization",
        ),
        ForeignKeyConstraint(
            ["teacher_id", "institution_id"],
            ["teachers.id", "teachers.institution_id"],
            name="fk_source_teacher_same_institution",
        ),
    )

    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(128), index=True)
    board_or_exam: Mapped[str | None] = mapped_column(String(255), index=True)
    academic_year: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    copyright_classification: Mapped[str | None] = mapped_column(String(128))
    trust_tier: Mapped[str] = mapped_column(
        String(64),
        default=SourceTrustTier.ANALYTICAL.value,
        nullable=False,
    )
    anythingllm_workspace: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(32),
        default=SourceStatus.STAGED.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    revisions: Mapped[list[SourceRevision]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="SourceRevision.revision_number",
    )

    @staticmethod
    def official_type_values() -> tuple[str, ...]:
        return (
            SourceType.OFFICIAL_AUTHORITY.value,
            SourceType.OFFICIAL_SYLLABUS.value,
            SourceType.OFFICIAL_EXAM_BULLETIN.value,
            SourceType.OFFICIAL_PAPER.value,
            SourceType.ANSWER_KEY.value,
            SourceType.MARKING_SCHEME.value,
            SourceType.SAMPLE_PAPER.value,
        )


class SourceRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "revision_number", name="uq_source_revision_number"),
        UniqueConstraint(
            "source_id",
            "checksum",
            "source_snapshot_checksum",
            name="uq_source_revision_identity",
        ),
        UniqueConstraint("source_id", "active_slot", name="uq_source_single_active_revision"),
        CheckConstraint(
            "(status = 'active' AND active_slot = 1) OR "
            "(status <> 'active' AND active_slot IS NULL)",
            name="ck_source_revision_active_slot",
        ),
    )

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ingestion_method: Mapped[str] = mapped_column(
        String(32),
        default=SourceIngestionMethod.MANUAL.value,
        nullable=False,
        index=True,
    )
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_snapshot_checksum: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        String(32),
        default=SourceExtractionStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_checksum: Mapped[str | None] = mapped_column(String(64))
    validated_checksum: Mapped[str | None] = mapped_column(String(64))
    approval_fingerprint: Mapped[str | None] = mapped_column(String(64))
    extraction_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=SourceRevisionStatus.STAGED.value,
        nullable=False,
        index=True,
    )
    active_slot: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anythingllm_document_id: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source: Mapped[Source] = relationship(back_populates="revisions")
    curriculum_versions: Mapped[list[CurriculumVersion]] = relationship(
        secondary=curriculum_version_source_revisions
    )
    exam_versions: Mapped[list[ExamVersion]] = relationship(
        secondary=exam_version_source_revisions
    )
    questions: Mapped[list[Question]] = relationship(secondary=question_source_revisions)
    policy_rules: Mapped[list[PolicyRule]] = relationship(secondary=policy_rule_source_revisions)


class SourceDiff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_diffs"
    __table_args__ = (
        UniqueConstraint(
            "to_revision_id",
            name="uq_source_diff_to_revision",
        ),
    )

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    from_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="CASCADE"), index=True
    )
    to_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="CASCADE"), index=True
    )
    checksum_changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_changes_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    content_diff_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)


class SourceAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_audit_events"

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
