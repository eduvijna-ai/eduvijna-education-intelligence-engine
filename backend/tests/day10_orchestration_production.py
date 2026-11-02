"""Deterministic production-scope orchestration seed for Day10 compiled-graph proofs."""

from __future__ import annotations

from pathlib import Path

from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    approve_mapping_with_curator,
    ensure_mapping_curator_credential,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_day10_r8_trust import _seed_production_institution_graph
from test_day10_r11_trust import (
    _MAPPING_SOURCE_LOCATOR,
    _approve_revision_mapping_binding,
)

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.curriculum import Competency, CurriculumNode, LearningOutcome
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import CurriculumNodeType
from app.models.source import SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.factory import build_orchestration_service
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.service import OrchestrationService
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
)
from app.root_cause_intelligence.mapping_claim_authority import MappingClaimApprovalContext
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def seed_day10_production_orchestration(
    session: Session,
    tmp_path: Path,
    *,
    adapter: FakeAnythingLLMAdapter | None = None,
) -> dict[str, str]:
    ctx = _seed_production_institution_graph(session)
    whole_add = session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == ctx["curriculum_version_id"],
            CurriculumNode.code == "whole-number-addition",
        )
    )
    if session.scalar(select(Competency).where(Competency.code == "application")) is None:
        from app.models.curriculum import EducationFramework

        fw = session.scalar(select(EducationFramework).limit(1))
        if fw is not None:
            session.add(
                Competency(
                    code="application",
                    name="Application",
                    framework=fw,
                    active=True,
                )
            )
    lo = LearningOutcome(
        curriculum_version_id=ctx["curriculum_version_id"],
        code="lo-d10-whole-add",
        text="Apply whole-number addition (synthetic fixture LO).",
        active=True,
        source_revision_id=ctx["source_revision_id"],
    )
    if whole_add is not None:
        lo.nodes.append(whole_add)
    session.add(lo)
    session.flush()
    ctx["learning_outcome_id"] = lo.id
    grade = session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == ctx["curriculum_version_id"],
            CurriculumNode.code == "grade-4",
        )
    )
    if grade is not None:
        grade.code = "grade-8"
        grade.title = "Grade 8"
        grade.metadata_json = {
            **(grade.metadata_json or {}),
            "authoritative_age_min": 12,
            "authoritative_age_max": 14,
        }
        for concept_code in (
            "counting-sequence",
            "whole-number-addition",
            "multi-step-addition",
        ):
            concept = session.scalar(
                select(CurriculumNode).where(
                    CurriculumNode.curriculum_version_id == ctx["curriculum_version_id"],
                    CurriculumNode.code == concept_code,
                )
            )
            if concept is not None and isinstance(concept.metadata_json, dict):
                concept.metadata_json = {
                    **concept.metadata_json,
                    "grade_year_code": "grade-8",
                }
        subject = session.scalar(
            select(CurriculumNode).where(
                CurriculumNode.curriculum_version_id == ctx["curriculum_version_id"],
                CurriculumNode.code == "mathematics",
                CurriculumNode.node_type == CurriculumNodeType.SUBJECT.value,
            )
        )
        if subject is not None:
            session.add(
                CurriculumNode(
                    curriculum_version_id=ctx["curriculum_version_id"],
                    parent_id=subject.id,
                    node_type=CurriculumNodeType.CONCEPT.value,
                    code="addition-whole",
                    title="Addition whole (taxonomy alias)",
                    metadata_json={
                        "grade_year_code": "grade-8",
                        "subject_code": "mathematics",
                    },
                )
            )
        session.flush()
    ctx["grade_year_code"] = "grade-8"
    ensure_mapping_curator_registry(session)
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_mapping_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    ensure_genuine_source_content_approval(
        session,
        tmp_path,
        ctx["source_revision_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    mapping_overlay = _approve_revision_mapping_binding(
        session, tmp_path, ctx["source_revision_id"], ctx
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    if revision is not None:
        revision.metadata_json = {
            **(revision.metadata_json or {}),
            "grade_year_code": "grade-8",
            "medium_code": "english",
            "subject_code": "mathematics",
            "concept_codes": [
                "whole-number-addition",
                "multi-step-addition",
                "addition-whole",
            ],
        }
        session.flush()
    ki_adapter = adapter or FakeAnythingLLMAdapter()
    index_source_revision(
        session,
        ki_adapter,
        ctx["source_revision_id"],
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    session.commit()
    return {
        **ctx,
        "grade_year_code": "grade-8",
        "medium_code": "english",
        "subject_code": "mathematics",
        "concept_codes": ["whole-number-addition", "addition-whole"],
        "citation_label": "cite-day10-prod-orch",
    }


def build_day10_production_orchestration_service(
    session: Session,
    tmp_path: Path,
    *,
    gateway: FakeGenerationGateway | None = None,
    memory_checkpointer: bool = True,
) -> tuple[dict[str, str], OrchestrationService, FakeGenerationGateway, FakeAnythingLLMAdapter]:
    ki_adapter = FakeAnythingLLMAdapter()
    ctx = seed_day10_production_orchestration(session, tmp_path, adapter=ki_adapter)
    gw = gateway or FakeGenerationGateway()
    service = build_orchestration_service(
        session,
        gateway=gw,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=memory_checkpointer,
        force_fake=True,
    )
    return ctx, service, gw, ki_adapter


def build_day10_production_orchestration_request(
    ctx: dict[str, str],
    *,
    idempotency_key: str,
    requested_count: int = 1,
    diagnostic_scenario: str = "diagnostic_clean_pass",
    diagnostic_by_slot: dict[str, str] | None = None,
) -> OrchestrationRequest:
    metadata: dict[str, object] = {
        "fixture_scenario": "human_review",
        "diagnostic_enrichment_enabled": True,
        "root_cause_enrichment_enabled": True,
        "deterministic_human_review_required": True,
        "partial_diagnostic_blocking_with_root_cause_pass": True,
        "diagnostic_fixture_scenario": diagnostic_scenario,
    }
    if diagnostic_by_slot:
        metadata["diagnostic_fixture_by_slot"] = diagnostic_by_slot
    if ctx.get("learning_outcome_id"):
        metadata["learning_outcome_ids"] = [ctx["learning_outcome_id"]]
    return OrchestrationRequest(
        idempotency_key=idempotency_key,
        requested_count=requested_count,
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code=ctx.get("grade_year_code", "grade-4"),
        medium_code=None,
        subject_code=ctx.get("subject_code", "mathematics"),
        concept_codes=list(
            ctx.get("concept_codes") or ["whole-number-addition", "addition-whole"]
        ),
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        retrieval_query="whole-number addition off-by-one-low maps multi-step",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        marks=1.0,
        max_repairs=2,
        metadata_json=metadata,
    )
