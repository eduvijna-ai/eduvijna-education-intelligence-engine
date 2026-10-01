from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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
    question_competencies,
    question_learning_outcomes,
    question_prerequisites,
    question_sources,
)
from app.models.enums import QuestionStatus, TestStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.curriculum import Competency, CurriculumNode, CurriculumVersion, LearningOutcome
    from app.models.diagnostic import DiagnosticTaxonomyEntry
    from app.models.examination import ExamVersion
    from app.models.source import Source


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "difficulty IS NULL OR (difficulty >= 1 AND difficulty <= 5)",
            name="ck_question_difficulty",
        ),
    )

    external_code: Mapped[str | None] = mapped_column(String(128), index=True)
    content_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    curriculum_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("curriculum_versions.id", ondelete="SET NULL"), index=True
    )
    exam_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("exam_versions.id", ondelete="SET NULL"), index=True
    )
    primary_curriculum_node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("curriculum_nodes.id", ondelete="SET NULL"), index=True
    )
    question_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stem_text: Mapped[str] = mapped_column(Text, nullable=False)
    stem_latex: Mapped[str | None] = mapped_column(Text)
    solution_text: Mapped[str | None] = mapped_column(Text)
    solution_latex: Mapped[str | None] = mapped_column(Text)
    answer_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    cognitive_level: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=QuestionStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    curriculum_version: Mapped[CurriculumVersion | None] = relationship()
    exam_version: Mapped[ExamVersion | None] = relationship()
    primary_curriculum_node: Mapped[CurriculumNode | None] = relationship(
        foreign_keys=[primary_curriculum_node_id]
    )
    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.sequence",
    )
    assets: Mapped[list[QuestionAsset]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionAsset.sequence",
    )
    competencies: Mapped[list[Competency]] = relationship(secondary=question_competencies)
    learning_outcomes: Mapped[list[LearningOutcome]] = relationship(
        secondary=question_learning_outcomes
    )
    prerequisite_concepts: Mapped[list[CurriculumNode]] = relationship(
        secondary=question_prerequisites
    )
    sources: Mapped[list[Source]] = relationship(secondary=question_sources)


class QuestionOption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "option_key", name="uq_question_option_key"),
    )

    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    option_key: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    latex: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diagnostic_taxonomy_entry_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("diagnostic_taxonomy_entries.id", ondelete="SET NULL"),
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    question: Mapped[Question] = relationship(back_populates="options")
    diagnostic_taxonomy_entry: Mapped[DiagnosticTaxonomyEntry | None] = relationship()


class QuestionAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_assets"

    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    uri: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    question: Mapped[Question] = relationship(back_populates="assets")


class TestDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_definitions"

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    curriculum_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("curriculum_versions.id", ondelete="SET NULL"), index=True
    )
    exam_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("exam_versions.id", ondelete="SET NULL"), index=True
    )
    blueprint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=TestStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    questions: Mapped[list[TestQuestion]] = relationship(
        back_populates="test_definition",
        cascade="all, delete-orphan",
        order_by="TestQuestion.sequence",
    )


class TestQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_questions"
    __table_args__ = (
        UniqueConstraint("test_definition_id", "sequence", name="uq_test_question_sequence"),
        UniqueConstraint("test_definition_id", "question_id", name="uq_test_question_question"),
    )

    test_definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_definitions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    section_code: Mapped[str | None] = mapped_column(String(128))
    marks: Mapped[float | None] = mapped_column(Float)
    negative_marks: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    test_definition: Mapped[TestDefinition] = relationship(back_populates="questions")
    question: Mapped[Question] = relationship()
