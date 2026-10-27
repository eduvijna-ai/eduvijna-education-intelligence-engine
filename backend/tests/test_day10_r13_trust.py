from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    _day9_audit,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r10_trust import (
    _paper_item_from_validated,
    _persist_day6_item,
)
from test_day10_r10_trust import (
    _session as _paper_session,
)
from test_day10_r11_trust import _approve_revision_mapping_binding

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.models.curriculum import ConceptPrerequisite, CurriculumNode
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.paper_distribution.contracts import DistributionTarget, PaperDistributionRequest
from app.paper_distribution.enums import PaperDistributionIssueCode, PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
)
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def test_tampered_loader_issues_blocks_production_root_cause(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    mapping_overlay = _approve_revision_mapping_binding(
        session, tmp_path, ctx["source_revision_id"]
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
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
    audit_id = "00000000-0000-4000-8000-000000000013"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    assert (snapshot.metadata_json or {}).get("loader_issue_count", 0) > 0
    forged_meta = {
        **(snapshot.metadata_json or {}),
        "loader_issues": [],
        "loader_issue_count": 0,
    }
    forged = snapshot.model_copy(update={"metadata_json": forged_meta})
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(ctx, forged, institution_id=INST_A),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert RootCauseIssueCode.UNAUTHORIZED_SOURCE in result.issue_codes


def test_evaluator_detects_mandatory_exact_count_conflict_before_merge(tmp_path: Path) -> None:
    session = _paper_session(tmp_path)
    ensure_paper_target_policy_configured(session)
    ctx = seed_cbse_fixture_curriculum(session)
    session.flush()
    _, validated_a = _persist_day6_item(session, ctx, f"item-{uuid4()}")
    _, validated_b = _persist_day6_item(session, ctx, f"item-{uuid4()}")
    _, validated_c = _persist_day6_item(session, ctx, f"item-{uuid4()}")
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
        paper_id="r13-mandatory-conflict",
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_count=3),
        ],
        items=[
            _paper_item_from_validated(validated_a).model_copy(
                update={"cognitive_level": "remember"}
            ),
            _paper_item_from_validated(validated_b).model_copy(
                update={"cognitive_level": "remember"}
            ),
            _paper_item_from_validated(validated_c).model_copy(
                update={"cognitive_level": "apply"}
            ),
        ],
    )
    session.commit()
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id="inst-r13", actor_id="actor-1"),
    )
    assert result.verdict != PaperDistributionVerdict.PASS
    assert PaperDistributionIssueCode.TARGET_INFEASIBLE in result.issue_codes


def test_unrelated_revision_without_mapping_binding_rejected(tmp_path: Path) -> None:
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
                        "candidate_concept_codes": ["whole-number-addition", "multi-step-addition"],
                        "source_revision_ids": [ctx["source_revision_id"]],
                        "source_locator": "forged/locator",
                        "mapping_evidence_checksum": "forged-checksum",
                    }
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000014"
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
    assert result.hypotheses == []
    assert result.verdict_status in {
        RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE,
        RootCauseVerdictStatus.FAIL,
    }


def test_hitl_orchestration_persists_diagnostic_and_root_cause_audits(tmp_path: Path) -> None:
    session = _session(tmp_path)
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        scenario="human_review",
        idempotency_key="d10-r13-hitl-orch",
        requested_count=2,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "root_cause_enrichment_enabled": True,
            }
        }
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.REVIEW_REQUIRED,
    }
    audit_session = service._control
    diagnostic_items = audit_session.scalars(
        select(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "diagnostic_item",
            OrchestrationAuditEvent.status == "pass",
        )
    ).all()
    assert diagnostic_items
    checkpoint = service._graph.get_state({"configurable": {"thread_id": completed.run_id}})
    attempts = (checkpoint.values or {}).get("node_attempts") or {}
    assert "diagnostic_enrich" in attempts
    assert "root_cause_enrich" in attempts
    first_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    replay = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert replay.run_id == completed.run_id
    second_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    assert second_count == first_count


def test_root_cause_enrich_node_persists_item_audit(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
    from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
    from app.orchestration.contracts import OrchestrationRequest
    from app.orchestration.nodes.root_cause import root_cause_enrich_node
    from app.orchestration.state import OrchestrationGraphState

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    mapping_overlay = _approve_revision_mapping_binding(
        session, tmp_path, ctx["source_revision_id"]
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000015"
    _day9_audit(
        session,
        ctx,
        audit_id=audit_id,
        run_id="run-r13-rc",
        request_hash="hash-r13-rc",
        evidence_refs=["cite-r13"],
    )
    session.commit()
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    request = OrchestrationRequest(
        idempotency_key="r13-rc-node-key",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    state: OrchestrationGraphState = {
        "run_id": "run-r13-rc",
        "request_hash": "hash-r13-rc",
        "request": request.model_dump(mode="json"),
        "root_cause_results": [],
        "diagnostic_validation": [{"item_id": "item-r8", "blocking": False}],
        "diagnostic_results": [
            {
                "item_id": "item-r8",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "audit_refs": [audit_id],
                "option_tags": [
                    {
                        "option_key": "A",
                        "is_correct": False,
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": ["cite-r13"],
                    }
                ],
            }
        ],
        "resolved_scope": {
            "curriculum_version_id": ctx["curriculum_version_id"],
            "organization_id": ctx["organization_id"],
            "institution_id": ctx["institution_id"],
            "grade_year_code": "grade-4",
            "subject_code": "mathematics",
            "concept_codes": ["multi-step-addition"],
        },
        "draft_items": [
            {
                "item_id": "item-r8",
                "concept_codes": ["multi-step-addition"],
                "source_revision_ids": [ctx["source_revision_id"]],
            }
        ],
        "deterministic_validation": [{"item_id": "item-r8", "blocking": False}],
        "knowledge_context": KnowledgeContextPack(
            query_id="r13-rc",
            query_text="addition",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[
                {
                    "source_id": ctx["source_id"],
                    "source_revision_id": ctx["source_revision_id"],
                    "source_revision_checksum": "a" * 64,
                    "binding_id": "bind-r13",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "R8 official prerequisite source",
                    "locator": "loc",
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite-r13",
                }
            ],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
    }
    before = session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "root_cause_item"
        )
    )
    update = root_cause_enrich_node(state, deps)
    after = session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "root_cause_item"
        )
    )
    assert after > before
    results = update.get("root_cause_results") or []
    assert len(results) == 1
    entry = results[0]
    assert entry.get("verdict_status") == RootCauseVerdictStatus.PASS.value
    assert entry.get("hypotheses")
