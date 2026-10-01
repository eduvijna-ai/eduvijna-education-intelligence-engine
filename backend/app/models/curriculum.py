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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import (
    curriculum_node_competencies,
    curriculum_node_learning_outcomes,
    curriculum_version_sources,
)
from app.models.enums import CurriculumStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source import Source


class EducationFramework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "education_frameworks"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    curriculum_packs: Mapped[list[CurriculumPack]] = relationship(back_populates="framework")


class CurriculumPack(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_packs"

    framework_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("education_frameworks.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(128), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    framework: Mapped[EducationFramework | None] = relationship(back_populates="curriculum_packs")
    versions: Mapped[list[CurriculumVersion]] = relationship(
        back_populates="curriculum_pack",
        cascade="all, delete-orphan",
    )


class CurriculumVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_versions"
    __table_args__ = (
        UniqueConstraint("curriculum_pack_id", "version_code", name="uq_curriculum_version_code"),
    )

    curriculum_pack_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_packs.id", ondelete="CASCADE"),
        index=True,
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    academic_year: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(32),
        default=CurriculumStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_pack: Mapped[CurriculumPack] = relationship(back_populates="versions")
    nodes: Mapped[list[CurriculumNode]] = relationship(
        back_populates="curriculum_version",
        cascade="all, delete-orphan",
    )
    learning_outcomes: Mapped[list[LearningOutcome]] = relationship(
        back_populates="curriculum_version",
        cascade="all, delete-orphan",
    )
    sources: Mapped[list[Source]] = relationship(secondary=curriculum_version_sources)


class CurriculumNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_nodes"
    __table_args__ = (
        UniqueConstraint(
            "curriculum_version_id",
            "parent_id",
            "node_type",
            "code",
            name="uq_curriculum_node_scope",
        ),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="nodes")
    parent: Mapped[CurriculumNode | None] = relationship(
        remote_side="CurriculumNode.id",
        back_populates="children",
    )
    children: Mapped[list[CurriculumNode]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    learning_outcomes: Mapped[list[LearningOutcome]] = relationship(
        secondary=curriculum_node_learning_outcomes,
        back_populates="nodes",
    )
    competencies: Mapped[list[Competency]] = relationship(
        secondary=curriculum_node_competencies,
        back_populates="nodes",
    )


class LearningOutcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learning_outcomes"
    __table_args__ = (
        UniqueConstraint("curriculum_version_id", "code", name="uq_learning_outcome_code"),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="learning_outcomes")
    nodes: Mapped[list[CurriculumNode]] = relationship(
        secondary=curriculum_node_learning_outcomes,
        back_populates="learning_outcomes",
    )


class Competency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competencies"

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    nodes: Mapped[list[CurriculumNode]] = relationship(
        secondary=curriculum_node_competencies,
        back_populates="competencies",
    )


class ConceptPrerequisite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concept_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "prerequisite_concept_id",
            "target_concept_id",
            name="uq_concept_prerequisite_edge",
        ),
        CheckConstraint(
            "prerequisite_concept_id <> target_concept_id",
            name="ck_concept_prerequisite_not_self",
        ),
        CheckConstraint("weight IS NULL OR (weight >= 0 AND weight <= 1)", name="ck_prereq_weight"),
    )

    prerequisite_concept_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    target_concept_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        default="prerequisite",
        nullable=False,
    )
    weight: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
