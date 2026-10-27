from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    INST_B,
    _day9_audit,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import SourceTrustTier, SourceType
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import Source, SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.fixtures import build_day8_test_service
from app.orchestration.graph import build_orchestration_graph
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    paper_targets_authorized,
)
from app.prerequisite_intelligence.authority import (
    load_revision_record,
    revision_is_authorized_for_scope,
)
from app.prerequisite_intelligence.contracts import (
    PrerequisiteGraphEdge,
    PrerequisiteGraphPath,
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphLifecycleStatus
from app.prerequisite_intelligence.fixtures import seed_day10_prerequisite_fixture
from app.root_cause_intelligence.contracts import RootCauseHypothesis
from app.root_cause_intelligence.enums import RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    apply_mapping_authority_overlay,
    mapping_entry_production_authorized,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.ranking import project_hypothesis_authorized_paths
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext

_APPROVED_MAPPING_OVERLAY_BASE = {
    "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
    "mapping_registry_version": "root-cause-mapping@v1",
    "candidate_concept_codes": ["whole-number-addition", "multi-step-addition"],
}


def _approved_mapping_overlay(**updates: object) -> dict[str, object]:
    return {**_APPROVED_MAPPING_OVERLAY_BASE, **updates}


def test_unsourced_mapping_overlay_does_not_authorize_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    {"misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"},
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000011"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    registry = apply_mapping_authority_overlay(
        session, load_root_cause_mapping()
    )
    entry = next(
        mapping
        for mapping in registry.mappings
        if mapping.misconception_code == "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"
    )
    assert entry.synthetic is True
    assert entry.source_revision_ids == []
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(ctx, snapshot, institution_id=INST_A),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert result.verdict_status in {
        RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE,
        RootCauseVerdictStatus.FAIL,
    }


def test_source_backed_mapping_overlay_production_positive(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    _approved_mapping_overlay(
                        source_revision_ids=[ctx["source_revision_id"]],
                    )
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000012"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    assert snapshot.nodes
    scope = snapshot.scope
    registry = apply_mapping_authority_overlay(
        session, load_root_cause_mapping()
    )
    entry = next(
        mapping
        for mapping in registry.mappings
        if mapping.misconception_code == "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"
    )
    revision_record = load_revision_record(session, ctx["source_revision_id"])
    assert revision_record is not None
    assert scope.curriculum_version_id in revision_record.bound_curriculum_version_ids
    assert revision_is_authorized_for_scope(
        revision_record,
        scope,
        scope.curriculum_version_id,
    )
    assert mapping_entry_production_authorized(
        session,
        entry,
        graph_scope=scope,
        allowed_option_revision_ids={ctx["source_revision_id"]},
    )
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    request = _root_cause_request(ctx, snapshot, institution_id=INST_A).model_copy(
        update={"curriculum_version_id": snapshot.scope.curriculum_version_id}
    )
    result = RootCauseIntelligenceService().analyze(
        request,
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses, result.issue_codes
    assert all(
        revision_id == ctx["source_revision_id"]
        for hypothesis in result.hypotheses
        for revision_id in hypothesis.evidence_revision_ids
    )


def test_cross_tenant_mapping_revision_blocked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    foreign_source = Source(
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Foreign",
        trust_tier=SourceTrustTier.INSTITUTION.value,
        organization_id=ctx["organization_id"],
        institution_id=INST_B,
    )
    session.add(foreign_source)
    session.flush()
    foreign_revision = SourceRevision(
        source_id=foreign_source.id,
        revision_number=1,
        checksum="c" * 64,
        source_snapshot_checksum="d" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="c" * 64,
        metadata_json={},
    )
    session.add(foreign_revision)
    session.flush()
    registry = load_root_cause_mapping()
    entry = next(
        mapping
        for mapping in registry.mappings
        if mapping.misconception_code == "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"
    ).model_copy(
        update={"synthetic": False, "source_revision_ids": [foreign_revision.id]}
    )
    snapshot = _load_snapshot(session, ctx)
    assert not mapping_entry_production_authorized(
        session,
        entry,
        graph_scope=snapshot.scope,
        allowed_option_revision_ids={foreign_revision.id, ctx["source_revision_id"]},
    )


def test_mapping_revision_not_leaked_outside_option_allowlist() -> None:
    edge_a = PrerequisiteGraphEdge(
        edge_id="e-a",
        prerequisite_concept_id="c1",
        target_concept_id="c2",
        provenance_class=EdgeProvenanceClass.INFERRED,
        source_revision_id="rev-a",
    )
    snapshot = PrerequisiteGraphSnapshot.model_construct(
        snapshot_id="snap",
        scope=PrerequisiteGraphScope(curriculum_version_id="cv-1"),
        checksum="abc",
        graph_version="v1",
        lifecycle_status=GraphLifecycleStatus.ACTIVE,
        assembled_at="2026-01-01T00:00:00Z",
        nodes=[],
        edges=[edge_a],
    )
    hypothesis = RootCauseHypothesis(
        hypothesis_id="h1",
        rank=1,
        concept_id="c1",
        concept_code="concept-a",
        support_score=1.0,
        paths=[
            PrerequisiteGraphPath.model_construct(
                path_id="p-a",
                concept_ids=["c1", "c2"],
                edge_ids=["e-a"],
                depth=1,
                total_weight=1.0,
            )
        ],
        evidence_revision_ids=["rev-a"],
        alternatives=[],
    )
    projected = project_hypothesis_authorized_paths(
        snapshot,
        hypothesis,
        {"rev-a"},
        ["rev-b"],
    )
    assert projected is not None
    assert projected.evidence_revision_ids == ["rev-a"]


def test_hypothesis_rerank_after_projection_matches_order(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    _approved_mapping_overlay(
                        source_revision_ids=[ctx["source_revision_id"]],
                    )
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000013"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(ctx, snapshot, institution_id=INST_A),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    ranks = [hypothesis.rank for hypothesis in result.hypotheses]
    assert ranks == list(range(1, len(ranks) + 1))
    for index, hypothesis in enumerate(result.hypotheses, start=1):
        assert hypothesis.rank == index


def test_mandatory_exact_percent_conflict_with_request(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == "paper_distribution",
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    assert row is not None
    row.payload_json = {
        **(row.payload_json or {}),
        "mandatory_cognitive_exact_percent": {"remember": 100.0},
    }
    session.flush()
    paper = PaperDistributionRequest(
        paper_id="r11-conflict",
        requested_count=1,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=50.0),
        ],
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            )
        ],
    )
    ok, path = paper_targets_authorized(session, paper, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is False
    assert path is not None and "exact_percent" in path


def test_orchestration_graph_idempotent_replay_preserves_audit_count(tmp_path: Path) -> None:
    session = _session(tmp_path)
    seed_day10_prerequisite_fixture(session)
    session.commit()
    _, service = build_day8_test_service(session)
    graph = build_orchestration_graph(
        service.dependencies, checkpointer=service.managed_checkpointer.saver
    )
    assert graph is not None
    request = OrchestrationRequest(
        idempotency_key="d10-r11-replay-key-0001",
        retrieval_profile_version="default@v1",
        requested_count=1,
        metadata_json={"root_cause_enrichment_enabled": True},
    )
    first = service.run(request)
    audit_count_after_first = session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    second = service.run(request)
    audit_count_after_second = session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    assert first.run_id == second.run_id
    assert audit_count_after_second == audit_count_after_first
