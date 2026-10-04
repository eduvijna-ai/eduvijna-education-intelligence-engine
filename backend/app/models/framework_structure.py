"""Versioned framework structure, independent of curriculum/chapter membership."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkStructureNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_structure_nodes"
    __table_args__ = (
        UniqueConstraint("framework_id", "code", name="uq_framework_structure_code"),
        UniqueConstraint(
            "id", "framework_id", "level", name="uq_framework_structure_id_scope_level"
        ),
        UniqueConstraint("competency_id", name="uq_framework_structure_competency"),
        ForeignKeyConstraint(
            ["parent_id", "framework_id", "parent_level"],
            [
                "framework_structure_nodes.id",
                "framework_structure_nodes.framework_id",
                "framework_structure_nodes.level",
            ],
            name="fk_framework_structure_parent_scope_level",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "level IN ('stage', 'curricular_area', 'goal', 'competency')",
            name="ck_framework_structure_level",
        ),
        CheckConstraint(
            "(level = 'stage' AND parent_id IS NULL AND parent_level IS NULL) OR "
            "(parent_id IS NOT NULL AND parent_level IS NOT NULL AND ("
            "(level = 'curricular_area' AND parent_level = 'stage') OR "
            "(level = 'goal' AND parent_level = 'curricular_area') OR "
            "(level = 'competency' AND parent_level = 'goal')))",
            name="ck_framework_structure_parent_level",
        ),
        CheckConstraint(
            "(level = 'competency' AND competency_id IS NOT NULL) OR "
            "(level <> 'competency' AND competency_id IS NULL)",
            name="ck_framework_structure_competency_leaf",
        ),
        CheckConstraint(
            "publication_status IN ('draft', 'final')",
            name="ck_framework_structure_publication_status",
        ),
        CheckConstraint(
            "review_status IN ('review_required', 'reviewed')",
            name="ck_framework_structure_review_status",
        ),
    )

    framework_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("education_frameworks.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Codes are stable normalized identities unique within a framework version;
    # official_code preserves local codes such as C3.2 that may recur in other areas.
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    official_code: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    official_text: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    parent_level: Mapped[str | None] = mapped_column(String(32))
    competency_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competencies.id", ondelete="RESTRICT"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    publication_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LearningOutcomeCompetencyLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learning_outcome_competency_links"
    __table_args__ = (
        UniqueConstraint(
            "learning_outcome_id",
            "competency_node_id",
            "relationship_type",
            "source_revision_id",
            name="uq_learning_outcome_competency_evidence",
        ),
        ForeignKeyConstraint(
            ["competency_node_id", "framework_id", "competency_node_level"],
            [
                "framework_structure_nodes.id",
                "framework_structure_nodes.framework_id",
                "framework_structure_nodes.level",
            ],
            name="fk_lo_competency_framework_leaf",
            ondelete="CASCADE",
        ),
        CheckConstraint("competency_node_level = 'competency'", name="ck_lo_competency_leaf"),
        CheckConstraint(
            "publication_status IN ('draft', 'final')", name="ck_lo_competency_publication_status"
        ),
        CheckConstraint(
            "review_status IN ('review_required', 'reviewed')",
            name="ck_lo_competency_review_status",
        ),
        CheckConstraint(
            "status IN ('direct', 'partial', 'unresolved', 'review_required')",
            name="ck_lo_competency_status",
        ),
        CheckConstraint(
            "status <> 'direct' OR (inferred = false AND review_status = 'reviewed' "
            "AND evidence_text IS NOT NULL)",
            name="ck_lo_competency_direct_evidence",
        ),
        CheckConstraint(
            "status = 'direct' OR inferred = true", name="ck_lo_competency_inferred_status"
        ),
    )

    curriculum_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    learning_outcome_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_outcomes.id", ondelete="CASCADE"), index=True
    )
    framework_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("education_frameworks.id", ondelete="CASCADE"), index=True
    )
    competency_node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competency_node_level: Mapped[str] = mapped_column(
        String(32), default="competency", nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inferred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    publication_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
