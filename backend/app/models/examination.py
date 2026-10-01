from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import exam_version_sources
from app.models.enums import ExamStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source import Source


class ExamPack(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_packs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_exam_pack_code"),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(128), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    versions: Mapped[list[ExamVersion]] = relationship(
        back_populates="exam_pack",
        cascade="all, delete-orphan",
    )


class ExamVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_versions"
    __table_args__ = (
        UniqueConstraint("exam_pack_id", "version_code", name="uq_exam_version_code"),
    )

    exam_pack_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exam_packs.id", ondelete="CASCADE"), index=True
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    academic_year: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    total_marks: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ExamStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    exam_pack: Mapped[ExamPack] = relationship(back_populates="versions")
    sections: Mapped[list[ExamSection]] = relationship(
        back_populates="exam_version",
        cascade="all, delete-orphan",
    )
    blueprint_rules: Mapped[list[ExamBlueprintRule]] = relationship(
        back_populates="exam_version",
        cascade="all, delete-orphan",
    )
    sources: Mapped[list[Source]] = relationship(secondary=exam_version_sources)


class ExamSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_sections"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "exam_version_id",
            name="uq_exam_section_id_version",
        ),
        UniqueConstraint(
            "exam_version_id",
            "parent_section_id",
            "code",
            name="uq_exam_section_scope",
        ),
        ForeignKeyConstraint(
            ["parent_section_id", "parent_exam_version_id"],
            ["exam_sections.id", "exam_sections.exam_version_id"],
            name="fk_exam_section_parent_same_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(parent_section_id IS NULL AND parent_exam_version_id IS NULL) OR "
            "(parent_section_id IS NOT NULL AND parent_exam_version_id = exam_version_id)",
            name="ck_exam_section_parent_version",
        ),
    )

    exam_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exam_versions.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[str | None] = mapped_column(String(36), index=True)
    parent_exam_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subject_code: Mapped[str | None] = mapped_column(String(128), index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    exam_version: Mapped[ExamVersion] = relationship(back_populates="sections")
    parent: Mapped[ExamSection | None] = relationship(
        remote_side=lambda: [ExamSection.id, ExamSection.exam_version_id],
        foreign_keys=lambda: [ExamSection.parent_section_id, ExamSection.parent_exam_version_id],
        back_populates="children",
    )
    children: Mapped[list[ExamSection]] = relationship(
        foreign_keys=lambda: [ExamSection.parent_section_id, ExamSection.parent_exam_version_id],
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    blueprint_rules: Mapped[list[ExamBlueprintRule]] = relationship(
        back_populates="section",
        foreign_keys=lambda: [
            ExamBlueprintRule.section_id,
            ExamBlueprintRule.section_exam_version_id,
        ],
    )


class ExamBlueprintRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_blueprint_rules"
    __table_args__ = (
        CheckConstraint(
            "exact_count IS NULL OR exact_count >= 0",
            name="ck_rule_exact_nonnegative",
        ),
        CheckConstraint("min_count IS NULL OR min_count >= 0", name="ck_rule_min_nonnegative"),
        CheckConstraint("max_count IS NULL OR max_count >= 0", name="ck_rule_max_nonnegative"),
        CheckConstraint(
            "min_count IS NULL OR max_count IS NULL OR min_count <= max_count",
            name="ck_rule_min_lte_max",
        ),
        CheckConstraint(
            "exact_count IS NULL OR min_count IS NULL OR exact_count >= min_count",
            name="ck_rule_exact_gte_min",
        ),
        CheckConstraint(
            "exact_count IS NULL OR max_count IS NULL OR exact_count <= max_count",
            name="ck_rule_exact_lte_max",
        ),
        ForeignKeyConstraint(
            ["section_id", "section_exam_version_id"],
            ["exam_sections.id", "exam_sections.exam_version_id"],
            name="fk_blueprint_section_same_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(section_id IS NULL AND section_exam_version_id IS NULL) OR "
            "(section_id IS NOT NULL AND section_exam_version_id = exam_version_id)",
            name="ck_blueprint_section_version",
        ),
    )

    exam_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exam_versions.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[str | None] = mapped_column(String(36), index=True)
    section_exam_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selector_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    exact_count: Mapped[int | None] = mapped_column(Integer)
    min_count: Mapped[int | None] = mapped_column(Integer)
    max_count: Mapped[int | None] = mapped_column(Integer)
    marks_per_question: Mapped[float | None] = mapped_column(Float)
    negative_marks: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    exam_version: Mapped[ExamVersion] = relationship(back_populates="blueprint_rules")
    section: Mapped[ExamSection | None] = relationship(
        back_populates="blueprint_rules",
        foreign_keys=[section_id, section_exam_version_id],
    )
