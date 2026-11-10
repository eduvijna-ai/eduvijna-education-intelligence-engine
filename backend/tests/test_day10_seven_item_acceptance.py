"""Founder-authorized D10-12/19/22/28/29/32/33 consolidated acceptance proofs."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_day6_binding import seed_production_day6_audit
from day10_orchestration_production import (
    build_day10_production_orchestration_request,
    build_day10_production_orchestration_service,
)
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_teacher_for_scope,
    mandatory_board_policy_rule,
    mandatory_institution_policy_rule,
    mandatory_teacher_policy_rule,
)
from sqlalchemy import func, select  # noqa: F401 — used in nested helpers
from test_day10_r8_trust import (
    INST_A,
    INST_B,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import (
    _approve_revision_mapping_binding,
)
from test_day10_r17_trust import _bootstrap_mapping_curator
from test_day10_r18_trust import (
    _approve_mandatory_policy_for_rule,
    _paper_item_from_validated,
)

from app.common.trust_execution import TrustExecutionMode
from app.models.education_intelligence import PolicyRegistryEntry, ValidationAuditRun
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.human_decision import HumanResumeDecision
from app.paper_distribution.contracts import DistributionTarget, PaperDistributionRequest
from app.paper_distribution.enums import (
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import (
    evaluate_paper_distribution_with_session,
    reconcile_exact_counts,
)
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.enums import GraphAuditStatus
from app.prerequisite_intelligence.graph_verify import verify_production_graph_snapshot
from app.root_cause_intelligence.day6_binding_verify import verify_production_day6_binding
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    apply_mapping_authority_overlay,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    approve_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping, mapping_catalogue
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def test_d10_12_mapping_catalogue_overlay_and_unknown_misconception(tmp_path: Path) -> None:
    version, entries = mapping_catalogue()
    assert version == "root-cause-mapping@v1"
    assert {entry.misconception_code for entry in entries} == {
        "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        "MATH.ADD.WHOLE.SUM_AS_NEXT",
    }
    assert all(entry.synthetic for entry in entries)
    assert all(entry.version == "1" for entry in entries)

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    overlay = _approve_revision_mapping_binding(session, tmp_path, ctx["source_revision_id"], ctx)
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [overlay]},
        )
    )
    session.flush()
    base = load_root_cause_mapping()
    resolved = apply_mapping_authority_overlay(
        session,
        base,
        graph_scope=_load_snapshot(session, ctx).scope,
    )
    mapped = resolved.resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert mapped is not None
    assert mapped.source_revision_ids
    assert not mapped.synthetic

    snapshot = _load_snapshot(session, ctx)
    unknown_base = _root_cause_request(ctx, snapshot, institution_id=INST_A)
    unknown = RootCauseIntelligenceService().analyze(
        unknown_base.model_copy(
            update={
                "misconception_code": "MATH.UNKNOWN.NOT_IN_CATALOGUE",
                "tag": unknown_base.tag.model_copy(
                    update={"misconception_code": "MATH.UNKNOWN.NOT_IN_CATALOGUE"}
                ),
            }
        ),
        execution_mode=TrustExecutionMode.PRODUCTION,
        domain_session=session,
    )
    assert unknown.verdict_status == RootCauseVerdictStatus.FAIL
    assert RootCauseIssueCode.UNKNOWN_MISCONCEPTION in unknown.issue_codes
    assert not unknown.hypotheses


def test_d10_19_lo_competency_curriculum_and_day6_blocking_matrix(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    item_id = "d10-19-matrix-item"
    run_id, validated = seed_production_day6_audit(
        session,
        item_id=item_id,
        organization_id=ctx["organization_id"],
        institution_id=INST_A,
        curriculum_version_id=ctx["curriculum_version_id"],
        declared_cognitive_level="apply",
    )
    record = session.get(ValidationAuditRun, run_id)
    assert record is not None
    validated_items = list((record.metadata_json or {}).get("validated_items") or [])
    entry = validated_items[0]
    los = list(entry.get("learning_outcome_ids") or [])
    competencies = list(entry.get("competency_codes") or [])
    ok, _ = verify_production_day6_binding(
        session,
        item_id=item_id,
        validation_run_id=run_id,
        input_hash=str(entry.get("input_hash")),
        learning_outcome_ids=los,
        competency_codes=competencies,
        organization_id=ctx["organization_id"],
        institution_id=INST_A,
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    assert ok
    bad_lo, reason = verify_production_day6_binding(
        session,
        item_id=item_id,
        validation_run_id=run_id,
        input_hash=str(entry.get("input_hash")),
        learning_outcome_ids=["lo-foreign"],
        competency_codes=competencies,
        institution_id=INST_A,
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    assert not bad_lo
    assert reason == "learning_outcome_ids"
    foreign_inst, reason2 = verify_production_day6_binding(
        session,
        item_id=item_id,
        validation_run_id=run_id,
        input_hash=str(entry.get("input_hash")),
        learning_outcome_ids=los,
        competency_codes=competencies,
        institution_id=INST_B,
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    assert not foreign_inst
    assert reason2 == "institution_id"

    snapshot = _load_snapshot(session, ctx)
    base_request = _root_cause_request(ctx, snapshot, institution_id=INST_A)
    blocking_request = base_request.model_copy(
        update={
            "day6_blocking": True,
            "day6_validation_run_id": run_id,
            "day6_input_hash": str(entry.get("input_hash")),
            "learning_outcome_ids": los,
            "competency_codes": competencies,
        }
    )
    blocking_result = RootCauseIntelligenceService().analyze(
        blocking_request,
        execution_mode=TrustExecutionMode.PRODUCTION,
        domain_session=session,
    )
    assert blocking_result.verdict_status != RootCauseVerdictStatus.PASS
    assert RootCauseIssueCode.DAY6_BLOCKING in blocking_result.issue_codes
    assert not blocking_result.hypotheses


def test_d10_22_orchestration_interrupt_resume_identical_root_cause(tmp_path: Path) -> None:
    domain = _session(tmp_path)
    gateway = __import__(
        "app.orchestration.gateway.fake", fromlist=["FakeGenerationGateway"]
    ).FakeGenerationGateway()
    ctx, service, _gw, ki_adapter = build_day10_production_orchestration_service(
        domain,
        tmp_path,
        gateway=gateway,
        memory_checkpointer=False,
    )
    request = build_day10_production_orchestration_request(
        ctx,
        idempotency_key="d10-seven-hitl",
        requested_count=1,
        diagnostic_by_slot={"0": "diagnostic_clean_pass"},
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED, completed.errors
    root_rows = list(completed.metadata_json.get("root_cause_results") or [])
    assert any(
        str(row.get("verdict_status")) == RootCauseVerdictStatus.PASS.value
        and row.get("hypotheses")
        for row in root_rows
    )
    audit_before = domain.scalar(select(func.count()).select_from(OrchestrationAuditEvent))
    gateway_calls = len(gateway.call_history())
    service.close()
    service2 = build_orchestration_service(
        domain,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=False,
        force_fake=True,
    )
    replay = service2.run(request, resume=HumanResumeDecision(action="approve"))
    assert replay.run_id == completed.run_id
    assert replay.status == OrchestrationRunStatus.COMPLETED
    assert len(gateway.call_history()) == gateway_calls
    assert domain.scalar(select(func.count()).select_from(OrchestrationAuditEvent)) == audit_before
    service2.close()


def test_d10_28_29_three_tier_mandatory_and_quota_reconcile(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=2),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": EDUVIJNA_DEMO_BOARD_CODE}
    teacher = ensure_teacher_for_scope(
        session, institution_id=INST_A, external_code="teacher-d10-seven"
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = mandatory_board_policy_rule(
        value_json={
            "mandatory_cognitive_ranges": [
                {"key": "remember", "exact_count": 2},
                {"key": "apply", "min_percent": 30.0, "max_percent": 50.0},
            ]
        },
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    inst_rule = mandatory_institution_policy_rule(
        institution_id=INST_A,
        value_json={
            "mandatory_cognitive_ranges": [
                {"key": "apply", "min_percent": 35.0, "max_percent": 45.0},
            ]
        },
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    teacher_rule = mandatory_teacher_policy_rule(
        teacher_id=teacher.id,
        value_json={
            "mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}],
        },
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    session.add(board_rule)
    session.add(inst_rule)
    session.add(teacher_rule)
    session.flush()
    revision.policy_rules.extend([board_rule, inst_rule, teacher_rule])
    for rule in (board_rule, inst_rule, teacher_rule):
        _approve_mandatory_policy_for_rule(
            session,
            rule=rule,
            revision_id=revision.id,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
        )
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        teacher_id=teacher.id,
    )
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert not merged.get("mandatory_resolution_errors")
    ranges = {str(r["key"]): r for r in merged.get("mandatory_cognitive_ranges") or []}
    assert int(ranges["remember"]["exact_count"]) == 2
    assert float(ranges["apply"]["min_percent"]) >= 35.0
    assert float(ranges["apply"]["max_percent"]) <= 45.0

    targets = [
        DistributionTarget(dimension="cognitive", key="remember", exact_percent=33.0),
        DistributionTarget(dimension="cognitive", key="understand", exact_percent=33.0),
        DistributionTarget(dimension="cognitive", key="apply", exact_percent=34.0),
    ]
    assert reconcile_exact_counts(3, targets) == {
        "remember": 1,
        "understand": 1,
        "apply": 1,
    }


def test_d10_32_adversarial_production_path_smoke(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    snapshot_a = _load_snapshot(session, ctx)
    issues, _, blocking, _ = verify_production_graph_snapshot(
        session,
        snapshot_a,
        organization_id=ctx["organization_id"],
        institution_id=INST_B,
        teacher_id=None,
        execution_mode=TrustExecutionMode.PRODUCTION,
    )
    assert blocking
    assert RootCauseIssueCode.FOREIGN_TENANT in issues or RootCauseIssueCode.MISSING_GRAPH in issues

    from sqlalchemy import select

    from app.models.curriculum import ConceptPrerequisite
    from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphIssueCode
    from app.prerequisite_intelligence.fixtures import (
        load_day10_fixture_snapshot,
        seed_day10_prerequisite_fixture,
    )

    fixture_ctx = seed_day10_prerequisite_fixture(session)
    edge = session.scalars(
        select(ConceptPrerequisite).where(
            ConceptPrerequisite.prerequisite_concept_id == fixture_ctx["counting_concept_id"],
            ConceptPrerequisite.target_concept_id == fixture_ctx["whole_add_concept_id"],
        )
    ).first()
    assert edge is not None
    edge.metadata_json = {
        "provenance_class": EdgeProvenanceClass.OFFICIAL.value,
        "source_revision_id": fixture_ctx["source_revision_id"],
        "source_locator": "forged",
    }
    session.commit()
    fixture_snapshot = load_day10_fixture_snapshot(session, fixture_ctx)
    assert all(e.provenance_class != EdgeProvenanceClass.OFFICIAL for e in fixture_snapshot.edges)
    forged_report = build_graph_quality_report(fixture_snapshot, allowed_source_revision_ids=set())
    assert forged_report.status == GraphAuditStatus.FAIL
    assert any(
        issue.code == GraphIssueCode.UNAUTHORIZED_PROVENANCE for issue in forged_report.issues
    )

    actor_id, _ = _bootstrap_mapping_curator(session, ctx)
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator="forged/locator",
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=actor_id,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            curator_decision_token="not-a-token",
        )


def test_d10_33_paper_replay_idempotent_under_same_day6_binding_set(tmp_path: Path) -> None:
    from uuid import uuid4

    from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
    from app.education_intelligence.service import EducationIntelligenceValidationService
    from app.paper_distribution.audit import persist_paper_distribution_audit
    from app.paper_distribution.trusted_validation import PaperDay6ItemBinding

    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    ensure_paper_target_policy_configured(session)
    ctx = seed_cbse_fixture_curriculum(session)
    ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    session.flush()
    service = EducationIntelligenceValidationService(session)

    def _persist(item_suffix: str) -> tuple[str, dict]:
        item = positive_cbse_item(ctx).model_copy(
            update={
                "item_id": f"d10-33-{item_suffix}",
                "institution_id": INST_A,
                "metadata_json": {"paper_marks": 1.0},
            }
        )
        summary = service.validate_item(
            item,
            board_code="cbse",
            persist=True,
            actor_id="actor-d10-33",
            trusted_scope={
                "organization_id": ctx["organization_id"],
                "institution_id": INST_A,
                "curriculum_version_id": ctx["curriculum_version_id"],
            },
        )
        record = session.scalars(
            select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
        ).first()
        assert record is not None
        validated = (record.metadata_json or {}).get("validated_items", [])[0]
        return str(record.id), validated

    run_a, val_a = _persist(str(uuid4())[:8])
    run_b, val_b = _persist(str(uuid4())[:8])
    session.commit()
    trust = PaperDay6TrustContext.from_item_bindings(
        [
            PaperDay6ItemBinding(item_id=str(val_a["item_id"]), validation_run_id=run_a),
            PaperDay6ItemBinding(item_id=str(val_b["item_id"]), validation_run_id=run_b),
        ]
    )
    paper = PaperDistributionRequest(
        paper_id="d10-33-replay",
        requested_count=2,
        items=[_paper_item_from_validated(val_a), _paper_item_from_validated(val_b)],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        organization_id=graph_ctx["organization_id"],
    )
    first = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert first.verdict == PaperDistributionVerdict.PASS, first.issue_codes
    identity = trust.day6_audit_identity_digest()
    audit_a = persist_paper_distribution_audit(
        session,
        paper,
        first,
        execution_context=exec_ctx,
        execution_mode=TrustExecutionMode.PRODUCTION,
        day6_validation_identity=identity,
    )
    session.flush()
    audit_b = persist_paper_distribution_audit(
        session,
        paper,
        first,
        execution_context=exec_ctx,
        execution_mode=TrustExecutionMode.PRODUCTION,
        day6_validation_identity=identity,
    )
    assert audit_a == audit_b
