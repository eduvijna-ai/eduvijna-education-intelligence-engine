from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.education_intelligence.policy_registry import PolicyRegistry, load_policy_registry
from app.education_intelligence.quality_rule_pack import QualityRulePack, load_quality_rule_pack
from app.education_intelligence.safety_rules import SafetyRulePack, load_safety_rule_pack
from app.education_intelligence.scope import CurriculumScopeIndex
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry, load_taxonomy_registry
from app.models.curriculum import (
    Competency,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    LearningOutcome,
)


def _build_scope_index(session: Session, curriculum_version_id: str) -> CurriculumScopeIndex:
    version = session.get(CurriculumVersion, curriculum_version_id)
    framework_id = None
    if version and version.curriculum_pack_id:
        pack = session.get(CurriculumPack, version.curriculum_pack_id)
        if pack:
            framework_id = pack.framework_id
    los = session.scalars(
        select(LearningOutcome)
        .where(LearningOutcome.curriculum_version_id == curriculum_version_id)
        .options(selectinload(LearningOutcome.nodes))
    ).all()
    nodes = session.scalars(
        select(CurriculumNode).where(CurriculumNode.curriculum_version_id == curriculum_version_id)
    ).all()
    comp_query = select(Competency).options(selectinload(Competency.nodes))
    if framework_id:
        comp_query = comp_query.where(Competency.framework_id == framework_id)
    competencies = session.scalars(comp_query).all()
    index = CurriculumScopeIndex(
        learning_outcomes={lo.id: lo for lo in los},
        competencies_by_id={c.id: c for c in competencies},
        nodes_by_id={n.id: n for n in nodes},
        nodes_by_code={n.code: n for n in nodes},
        curriculum_version_id=curriculum_version_id,
        framework_id=framework_id,
    )
    for node in nodes:
        if node.node_type == "grade_year":
            meta = node.metadata_json or {}
            age_min = meta.get("authoritative_age_min")
            age_max = meta.get("authoritative_age_max")
            if age_min is not None and age_max is not None:
                index.grade_authoritative_age[node.code] = (int(age_min), int(age_max))
    for lo in los:
        scopes = []
        for node in lo.nodes:
            if node.curriculum_version_id == curriculum_version_id:
                scopes.append(index.scope_for_node(node))
        index.lo_scopes[lo.id] = scopes
    for comp in competencies:
        scopes = []
        for node in comp.nodes:
            if node.curriculum_version_id == curriculum_version_id:
                scopes.append(index.scope_for_node(node))
        index.competency_scopes[comp.id] = scopes
    return index


@dataclass
class ValidationContext:
    session: Session | None
    taxonomy: TaxonomyRegistry
    policy: PolicyRegistry
    curriculum_index: CurriculumScopeIndex | None = None
    board_code: str | None = None
    quality_rule_pack: QualityRulePack | None = None
    safety_rule_pack: SafetyRulePack | None = None

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
            index = _build_scope_index(session, curriculum_version_id)
        quality = load_quality_rule_pack(session)
        safety = load_safety_rule_pack(session, policy.version)
        return cls(
            session=session,
            taxonomy=taxonomy,
            policy=policy,
            curriculum_index=index,
            board_code=board_code,
            quality_rule_pack=quality,
            safety_rule_pack=safety,
        )
