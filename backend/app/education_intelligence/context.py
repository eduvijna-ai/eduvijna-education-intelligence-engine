from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.policy_registry import PolicyRegistry, load_policy_registry
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry, load_taxonomy_registry
from app.models.curriculum import Competency, CurriculumNode, LearningOutcome


@dataclass
class CurriculumScopeIndex:
    learning_outcomes: dict[str, LearningOutcome] = field(default_factory=dict)
    competencies_by_code: dict[str, Competency] = field(default_factory=dict)
    nodes_by_code: dict[str, CurriculumNode] = field(default_factory=dict)

    @classmethod
    def build(cls, session: Session, curriculum_version_id: str) -> CurriculumScopeIndex:
        los = session.scalars(
            select(LearningOutcome).where(
                LearningOutcome.curriculum_version_id == curriculum_version_id
            )
        ).all()
        nodes = session.scalars(
            select(CurriculumNode).where(
                CurriculumNode.curriculum_version_id == curriculum_version_id
            )
        ).all()
        competencies = session.scalars(select(Competency)).all()
        return cls(
            learning_outcomes={lo.id: lo for lo in los},
            competencies_by_code={c.code: c for c in competencies},
            nodes_by_code={n.code: n for n in nodes},
        )


@dataclass
class ValidationContext:
    session: Session | None
    taxonomy: TaxonomyRegistry
    policy: PolicyRegistry
    curriculum_index: CurriculumScopeIndex | None = None
    board_code: str | None = None
    quality_rule_pack_version: str = "quality-v1.0"

    @classmethod
    def create(
        cls,
        session: Session | None = None,
        *,
        curriculum_version_id: str | None = None,
        board_code: str | None = None,
    ) -> ValidationContext:
        taxonomy = load_taxonomy_registry(session)
        policy = load_policy_registry(session)
        index = None
        if session and curriculum_version_id:
            index = CurriculumScopeIndex.build(session, curriculum_version_id)
        return cls(
            session=session,
            taxonomy=taxonomy,
            policy=policy,
            curriculum_index=index,
            board_code=board_code,
        )
