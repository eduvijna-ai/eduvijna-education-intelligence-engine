# ruff: noqa: I001
from sqlalchemy import CheckConstraint, Column, ForeignKey, ForeignKeyConstraint, String, Table

from app.db.base import Base


curriculum_version_sources = Table(
    "curriculum_version_sources",
    Base.metadata,
    Column(
        "curriculum_version_id",
        String(36),
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

curriculum_node_learning_outcomes = Table(
    "curriculum_node_learning_outcomes",
    Base.metadata,
    Column(
        "curriculum_node_id",
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "learning_outcome_id",
        String(36),
        ForeignKey("learning_outcomes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

curriculum_node_competencies = Table(
    "curriculum_node_competencies",
    Base.metadata,
    Column(
        "curriculum_node_id",
        String(36),
        ForeignKey("curriculum_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "competency_id",
        String(36),
        ForeignKey("competencies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

exam_version_sources = Table(
    "exam_version_sources",
    Base.metadata,
    Column(
        "exam_version_id",
        String(36),
        ForeignKey("exam_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

question_competencies = Table(
    "question_competencies",
    Base.metadata,
    Column(
        "question_id",
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "competency_id",
        String(36),
        ForeignKey("competencies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

question_learning_outcomes = Table(
    "question_learning_outcomes",
    Base.metadata,
    Column(
        "question_id",
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "learning_outcome_id",
        String(36),
        ForeignKey("learning_outcomes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

question_prerequisites = Table(
    "question_prerequisites",
    Base.metadata,
    Column(
        "question_id",
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "concept_node_id",
        String(36),
        primary_key=True,
    ),
    Column(
        "concept_node_type",
        String(32),
        nullable=False,
        server_default="concept",
    ),
    ForeignKeyConstraint(
        ["concept_node_id", "concept_node_type"],
        ["curriculum_nodes.id", "curriculum_nodes.node_type"],
        name="fk_question_prerequisite_is_concept",
        ondelete="CASCADE",
    ),
    CheckConstraint(
        "concept_node_type = 'concept'",
        name="ck_question_prerequisite_type",
    ),
)

question_sources = Table(
    "question_sources",
    Base.metadata,
    Column(
        "question_id",
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

policy_rule_sources = Table(
    "policy_rule_sources",
    Base.metadata,
    Column(
        "policy_rule_id",
        String(36),
        ForeignKey("policy_rules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
