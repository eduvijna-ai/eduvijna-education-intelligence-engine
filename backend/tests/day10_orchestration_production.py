"""Deterministic production-scope orchestration seed for Day10 compiled-graph proofs."""

from __future__ import annotations

from pathlib import Path

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
from app.models.curriculum import CurriculumNode
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.source import SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.factory import build_orchestration_service
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.service import OrchestrationService
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    approve_root_cause_mapping_claim,
    issue_mapping_claim_writer_attestation,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def seed_day10_production_orchestration(
    session: Session,
    tmp_path: Path,
    *,
    adapter: FakeAnythingLLMAdapter | None = None,
) -> dict[str, str]:
    ctx = _seed_production_institution_graph(session)
    grade = session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == ctx["curriculum_version_id"],
            CurriculumNode.code == "grade-4",
        )
    )
    if grade is not None:
        grade.code = "grade-8"
        grade.title = "Grade 8"
        for concept_code in ("counting-sequence", "whole-number-addition", "multi-step-addition"):
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
        session.flush()
    ctx["grade_year_code"] = "grade-8"
    ensure_mapping_curator_registry(session)
    ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
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
    approve_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
        attestation=issue_mapping_claim_writer_attestation(session, approval_ctx),
    )
    ki_adapter = adapter or FakeAnythingLLMAdapter()
    index_source_revision(
        session,
        ki_adapter,
        ctx["source_revision_id"],
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    if revision is not None:
        revision.metadata_json = {
            **(revision.metadata_json or {}),
            "grade_year_code": "grade-8",
            "medium_code": "english",
            "subject_code": "mathematics",
            "concept_codes": ["addition-whole", "multi-step-addition"],
        }
        session.flush()
    session.commit()
    return {
        **ctx,
        "grade_year_code": "grade-8",
        "medium_code": "english",
        "subject_code": "mathematics",
        "concept_codes": ["multi-step-addition"],
        "citation_label": "cite-day10-prod-orch",
    }


def build_day10_production_orchestration_service(
    session: Session,
    tmp_path: Path,
    *,
    gateway: FakeGenerationGateway | None = None,
    memory_checkpointer: bool = True,
) -> tuple[dict[str, str], OrchestrationService, FakeGenerationGateway]:
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
    return ctx, service, gw


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
        "diagnostic_fixture_scenario": diagnostic_scenario,
        "diagnostic_authoring_concept_codes": [],
    }
    if diagnostic_by_slot:
        metadata["diagnostic_fixture_by_slot"] = diagnostic_by_slot
    return OrchestrationRequest(
        idempotency_key=idempotency_key,
        requested_count=requested_count,
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code=ctx.get("grade_year_code", "grade-4"),
        medium_code=None,
        subject_code=ctx.get("subject_code", "mathematics"),
        concept_codes=list(ctx.get("concept_codes") or ["multi-step-addition"]),
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        retrieval_query="multi-step addition whole numbers grade 4 mathematics",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        marks=1.0,
        max_repairs=2,
        metadata_json=metadata,
    )
