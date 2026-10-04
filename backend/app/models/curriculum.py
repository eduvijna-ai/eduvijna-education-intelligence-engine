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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import (
    curriculum_node_competencies,
    curriculum_node_learning_outcomes,
    curriculum_version_sources,
)
from app.models.enums import CurriculumNodeType, CurriculumStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source import Source


class EducationFramework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "education_frameworks"
    __table_args__ = (
        UniqueConstraint("code", name="uq_education_framework_code"),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(128), index=True)
    authority: Mapped[str | None] = mapped_column(String(255))
    version_code: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    curriculum_packs: Mapped[list[CurriculumPack]] = relationship(back_populates="framework")
    competencies: Mapped[list[Competency]] = relationship(back_populates="framework")


class CurriculumPack(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_packs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_curriculum_pack_code"),
    )

    framework_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("education_frameworks.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(128), index=True)
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
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
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
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
            "id",
            "curriculum_version_id",
            name="uq_curriculum_node_id_version",
        ),
        UniqueConstraint(
            "id",
            "node_type",
            name="uq_curriculum_node_id_type",
        ),
        UniqueConstraint(
            "curriculum_version_id",
            "parent_id",
            "code",
            name="uq_curriculum_node_scope",
        ),
        Index(
            "uq_curriculum_node_root_code",
            "curriculum_version_id",
            "code",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
            postgresql_where=text("parent_id IS NULL"),
        ),
        ForeignKeyConstraint(
            ["parent_id", "parent_version_id"],
            ["curriculum_nodes.id", "curriculum_nodes.curriculum_version_id"],
            name="fk_curriculum_node_parent_same_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(parent_id IS NULL AND parent_version_id IS NULL) OR "
            "(parent_id IS NOT NULL AND parent_version_id = curriculum_version_id)",
            name="ck_curriculum_node_parent_version",
        ),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    official_text: Mapped[str | None] = mapped_column(Text)
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="nodes")
    parent: Mapped[CurriculumNode | None] = relationship(
        remote_side=lambda: [CurriculumNode.id, CurriculumNode.curriculum_version_id],
        foreign_keys=lambda: [CurriculumNode.parent_id, CurriculumNode.parent_version_id],
        back_populates="children",
    )
    children: Mapped[list[CurriculumNode]] = relationship(
        foreign_keys=lambda: [CurriculumNode.parent_id, CurriculumNode.parent_version_id],
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
    normalized_text: Mapped[str | None] = mapped_column(Text)
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="learning_outcomes")
    nodes: Mapped[list[CurriculumNode]] = relationship(
        secondary=curriculum_node_learning_outcomes,
        back_populates="learning_outcomes",
    )


class Competency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competencies"
    __table_args__ = (
        UniqueConstraint("code", name="uq_competency_code"),
    )

    framework_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("education_frameworks.id", ondelete="SET NULL"), index=True
    )
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    official_text: Mapped[str | None] = mapped_column(Text)
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(1024))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    framework: Mapped[EducationFramework | None] = relationship(back_populates="competencies")
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
        ForeignKeyConstraint(
            ["prerequisite_concept_id", "prerequisite_concept_type"],
            ["curriculum_nodes.id", "curriculum_nodes.node_type"],
            name="fk_prerequisite_source_is_concept",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["target_concept_id", "target_concept_type"],
            ["curriculum_nodes.id", "curriculum_nodes.node_type"],
            name="fk_prerequisite_target_is_concept",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "prerequisite_concept_id <> target_concept_id",
            name="ck_concept_prerequisite_not_self",
        ),
        CheckConstraint(
            "prerequisite_concept_type = 'concept' AND target_concept_type = 'concept'",
            name="ck_concept_prerequisite_types",
        ),
        CheckConstraint("weight IS NULL OR (weight >= 0 AND weight <= 1)", name="ck_prereq_weight"),
    )

    prerequisite_concept_id: Mapped[str] = mapped_column(String(36), index=True)
    prerequisite_concept_type: Mapped[str] = mapped_column(
        String(32),
        default=CurriculumNodeType.CONCEPT.value,
        server_default=CurriculumNodeType.CONCEPT.value,
        nullable=False,
    )
    target_concept_id: Mapped[str] = mapped_column(String(36), index=True)
    target_concept_type: Mapped[str] = mapped_column(
        String(32),
        default=CurriculumNodeType.CONCEPT.value,
        server_default=CurriculumNodeType.CONCEPT.value,
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        default="prerequisite",
        nullable=False,
    )
    weight: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    prerequisite_concept: Mapped[CurriculumNode] = relationship(
        foreign_keys=lambda: [
            ConceptPrerequisite.prerequisite_concept_id,
            ConceptPrerequisite.prerequisite_concept_type,
        ]
    )
    target_concept: Mapped[CurriculumNode] = relationship(
        foreign_keys=lambda: [
            ConceptPrerequisite.target_concept_id,
            ConceptPrerequisite.target_concept_type,
        ]
    )
