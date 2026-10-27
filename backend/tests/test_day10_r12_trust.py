from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    _day9_audit,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import _approved_mapping_overlay

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.models.curriculum import ConceptPrerequisite, CurriculumNode
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.graph import build_orchestration_graph
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import (
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    merge_mandatory_distribution_targets,
    paper_targets_authorized,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.root_cause_intelligence.enums import RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    apply_mapping_authority_overlay,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def test_mandatory_exact_count_enforced_with_existing_percent_target(tmp_path: Path) -> None:
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
        "mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}],
    }
    session.flush()
    paper = PaperDistributionRequest(
        paper_id="r12-mandatory-count",
        requested_count=3,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=100.0),
        ],
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q2",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q3",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
        ],
    )
    ok, path = paper_targets_authorized(session, paper, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is False
    assert path is not None and "exact_count" in path


def test_mandatory_exact_count_merged_and_passes_when_compatible(tmp_path: Path) -> None:
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
        "mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}],
    }
    session.flush()
    paper = PaperDistributionRequest(
        paper_id="r12-mandatory-pass",
        cognitive_targets=[],
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q2",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q3",
                marks=1.0,
                cognitive_level="apply",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
        ],
    )
    cognitive, _ = merge_mandatory_distribution_targets(paper, row.payload_json)
    remember = next(target for target in cognitive if target.key == "remember")
    assert remember.exact_count == 2
    merged = paper.model_copy(update={"cognitive_targets": cognitive})
    result = evaluate_paper_distribution(
        merged,
        taxonomy=TaxonomyRegistry(),
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
        data_session=session,
    )
    assert result.verdict == PaperDistributionVerdict.PASS


def test_fractional_competency_fifty_fifty_targets_pass() -> None:
    request = PaperDistributionRequest(
        paper_id="fractional-50-50",
        multi_label_policy=MultiLabelPolicy.FRACTIONAL_SPLIT,
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge", "application"],
                day6_validated=True,
            )
        ],
        competency_targets=[
            DistributionTarget(dimension="competency", key="knowledge", exact_percent=50.0),
            DistributionTarget(dimension="competency", key="application", exact_percent=50.0),
        ],
    )
    result = evaluate_paper_distribution(
        request,
        taxonomy=TaxonomyRegistry(),
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert result.verdict == PaperDistributionVerdict.PASS, result.issue_codes
    assert result.competency_summary.fractional_counts.get("knowledge") == 0.5
    assert result.competency_summary.fractional_counts.get("application") == 0.5
    assert PaperDistributionIssueCode.TARGET_MISMATCH not in result.issue_codes


def test_production_synthetic_sourced_edge_excluded_from_graph(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    multi_add = session.scalar(
        select(CurriculumNode).where(CurriculumNode.id == ctx["multi_add_concept_id"])
    )
    counting = session.scalar(
        select(CurriculumNode).where(CurriculumNode.code == "counting-sequence")
    )
    assert multi_add is not None and counting is not None
    session.add(
        ConceptPrerequisite(
            prerequisite_concept=counting,
            target_concept=multi_add,
            weight=0.5,
            metadata_json={
                "provenance_class": EdgeProvenanceClass.SYNTHETIC.value,
                "source_revision_id": ctx["source_revision_id"],
            },
        )
    )
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    synthetic_edges = [
        edge for edge in snapshot.edges if edge.provenance_class == EdgeProvenanceClass.SYNTHETIC
    ]
    assert synthetic_edges == []


def test_unrelated_mapping_overlay_candidate_codes_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    {
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "mapping_registry_version": "root-cause-mapping@v1",
                        "candidate_concept_codes": ["counting-sequence"],
                        "source_revision_ids": [ctx["source_revision_id"]],
                    }
                ]
            },
        )
    )
    session.commit()
    registry = apply_mapping_authority_overlay(session, load_root_cause_mapping())
    entry = registry.resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    assert entry.synthetic is True
    assert entry.source_revision_ids == []


def test_orchestration_diagnostic_and_root_cause_stages_run(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx, service = build_day8_test_service(session)
    graph = build_orchestration_graph(
        service.dependencies, checkpointer=service.managed_checkpointer.saver
    )
    assert graph is not None
    base_request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="d10-r12-orch-key-0001",
    )
    request = base_request.model_copy(
        update={
            "metadata_json": {
                **base_request.metadata_json,
                "root_cause_enrichment_enabled": True,
            }
        }
    )
    result = service.run(request)
    assert result.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.REVIEW_REQUIRED,
    }
    audit_session = service._control
    diagnostic_audits = audit_session.scalars(
        select(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "diagnostic_enrich"
        )
    ).all()
    assert diagnostic_audits
    checkpoint = service._graph.get_state(
        {"configurable": {"thread_id": result.run_id}}
    )
    attempts = (checkpoint.values or {}).get("node_attempts") or {}
    assert "diagnostic_enrich" in attempts
    assert "root_cause_enrich" in attempts
    assert "root_cause_enrichment_incomplete" not in result.errors
    first_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    replay = service.run(request)
    assert replay.run_id == result.run_id
    second_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    assert second_count == first_count


def test_approved_mapping_overlay_positive_production(tmp_path: Path) -> None:
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
    assert result.hypotheses
    assert result.verdict_status != RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE
