"""Day10 R29 — audit actor lineage, Day6 mark provenance, teacher weakening, rounding audit."""

from __future__ import annotations

from pathlib import Path

from day10_curator_auth import (
    approve_mapping_with_curator,
)
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_source_content_approval,
    ensure_teacher_for_scope,
    mandatory_board_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR
from test_day10_r18_trust import (
    _approve_mandatory_policy_for_rule,
    _bootstrap_mapping_curator,
    _paper_item_from_validated,
)
from test_day10_r20_trust import _apply_paper_with_day6_bindings
from test_day10_r27_trust import _bootstrap_mapping_curator as _bootstrap_mapping_curator_r27

from app.common.trust_execution import TrustExecutionMode
from app.curator_auth.issuer import verify_durable_curator_approval
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.education_intelligence.contracts import CognitiveDemandEvidence
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.models.education_intelligence import ValidationAuditRun
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionIssueCode, PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import mandatory_policy_claim_active
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    mapping_claim_authorized_for_overlay,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping

_COGNITIVE_LEVELS = {
    "remember": "Remember",
    "understand": "Understand",
    "apply": "Apply",
    "analyze": "Analyze",
    "evaluate": "Evaluate",
}


def _item_for_cognitive_level(base, level: str):
    canonical = _COGNITIVE_LEVELS.get(level.casefold(), level.strip().title())
    updates: dict = {"declared_cognitive_level": canonical}
    if canonical == "Remember":
        updates["cognitive_demand_evidence"] = CognitiveDemandEvidence(recall_required=True)
    elif canonical == "Understand":
        updates["cognitive_demand_evidence"] = CognitiveDemandEvidence(
            interpretation_required=True
        )
    elif canonical == "Apply":
        updates["cognitive_demand_evidence"] = CognitiveDemandEvidence(
            application_required=True
        )
    elif canonical == "Analyze":
        updates["cognitive_demand_evidence"] = CognitiveDemandEvidence(
            multi_step_reasoning=True
        )
    elif canonical == "Evaluate":
        updates["cognitive_demand_evidence"] = CognitiveDemandEvidence(
            comparison_or_evaluation=True
        )
    return base.model_copy(update=updates)


def _persist_real_day6_item(
    session,
    ctx: dict[str, str],
    item_id: str,
    *,
    paper_marks: float,
    declared_cognitive_level: str = "apply",
    institution_id: str | None = None,
) -> tuple[str, dict]:
    base = positive_cbse_item(ctx)
    item = _item_for_cognitive_level(base, declared_cognitive_level).model_copy(
        update={
            "item_id": item_id,
            "institution_id": institution_id or INST_A,
            "metadata_json": {
                **(base.metadata_json or {}),
                "paper_marks": paper_marks,
                "organization_id": ctx.get("organization_id"),
            },
        }
    )
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(
        item,
        board_code="cbse",
        persist=True,
        actor_id="founder-day10-trust",
        trusted_scope={
            "organization_id": ctx.get("organization_id"),
            "institution_id": institution_id or INST_A,
            "curriculum_version_id": ctx.get("curriculum_version_id"),
        },
    )
    assert not summary.blocking_failure
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    assert float(validated.get("marks") or 0) == paper_marks
    return str(record.id), validated


def test_mandatory_claim_inactive_when_audit_actor_null(tmp_path: Path) -> None:
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
    inst.metadata_json = {
        **(inst.metadata_json or {}),
        "board_code": EDUVIJNA_DEMO_BOARD_CODE,
    }
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "paper_mandatory_policy_claim_approved",
        )
    ).first()
    assert event is not None
    event.actor_id = None
    session.flush()
    assert not mandatory_policy_claim_active(
        session,
        rule_id=str(rule.id),
        revision_id=revision.id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_json=dict(rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=PaperExecutionContext(
            institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
        ),
    )


def test_mapping_claim_inactive_when_audit_actor_empty(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    approval_ctx = _bootstrap_mapping_curator_r27(session, ctx)
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    claim_id = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "root_cause_mapping_claim_approved",
        )
    ).first()
    assert event is not None
    event.actor_id = ""
    session.flush()
    overlay = {
        "misconception_code": entry.misconception_code,
        "candidate_concept_codes": list(entry.candidate_concept_codes),
        "source_locator": _MAPPING_SOURCE_LOCATOR,
        "mapping_registry_version": "root-cause-mapping@v1",
        "mapping_evidence_checksum": (event.payload_json or {}).get("mapping_evidence_checksum"),
        "source_span_checksum": (event.payload_json or {}).get("source_span_checksum"),
        "organization_id": ctx["organization_id"],
        "institution_id": ctx["institution_id"],
        "curriculum_version_id": ctx["curriculum_version_id"],
    }
    from app.prerequisite_intelligence.authority import load_revision_record
    from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope

    record = load_revision_record(session, ctx["source_revision_id"])
    assert record is not None
    assert not mapping_claim_authorized_for_overlay(
        session,
        record,
        entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=PrerequisiteGraphScope(
            curriculum_version_id=ctx["curriculum_version_id"],
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
        ),
    )
    assert claim_id


def test_verify_durable_rejects_blank_revoke_audit_actor(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, admin = _bootstrap_mapping_curator(session, ctx)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    claim_id = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
        admin_external_code=actor_id,
    )
    revoke_event = SourceAuditEvent(
        source_id=session.get(SourceRevision, ctx["source_revision_id"]).source_id,
        source_revision_id=ctx["source_revision_id"],
        event_type="root_cause_mapping_claim_revoked",
        actor_id="",
        outcome="success",
        payload_json={
            "claim_id": claim_id,
            "claim_status": "revoked",
            "approved_by": actor_id,
            "curator_approval": (  # invalid stub; durable verify must fail closed
                (session.scalars(
                    select(SourceAuditEvent).where(
                        SourceAuditEvent.event_type == "root_cause_mapping_claim_approved"
                    )
                ).first()
                or {}).payload_json
                or {}
            ).get("curator_approval"),
        },
    )
    session.add(revoke_event)
    session.flush()
    binding = {"revision_id": ctx["source_revision_id"], "claim_id": claim_id}
    assert not verify_durable_curator_approval(
        session,
        revoke_event.payload_json or {},
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_REVOKE,
        binding_payload=binding,
        source_audit_event_id=revoke_event.id,
        audit_actor_id="",
    )


def test_real_day6_marks_tamper_rejected_in_production_paper_eval(tmp_path: Path) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    ctx = graph_ctx
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=40.0),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {
        **(inst.metadata_json or {}),
        "board_code": EDUVIJNA_DEMO_BOARD_CODE,
    }
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    apply_board = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(apply_board)
    session.flush()
    revision.policy_rules.append(apply_board)
    _approve_mandatory_policy_for_rule(
        session,
        rule=apply_board,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)
    bindings: list[PaperDay6ItemBinding] = []
    items: list[PaperItemInput] = []
    for index in range(10):
        level = "apply" if index < 4 else "remember"
        marks = 1.0
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"real-day6-{index}",
            paper_marks=marks,
            declared_cognitive_level=level,
        )
        bindings.append(
            PaperDay6ItemBinding(
                item_id=str(validated["item_id"]), validation_run_id=run_id
            )
        )
        items.append(_paper_item_from_validated(validated))
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        organization_id=ctx["organization_id"],
    )
    trust = PaperDay6TrustContext.from_item_bindings(bindings)
    request = PaperDistributionRequest(
        paper_id="real-day6-marks-pass",
        items=items,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        include_mark_weighted=True,
    )
    ok = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert ok.verdict == PaperDistributionVerdict.PASS, ok.issue_codes
    assert ok.audit_ref
    tampered = [items[0].model_copy(update={"marks": 99.0}), *items[1:]]
    bad = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="real-day6-marks-fail",
            items=tampered,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in bad.issue_codes


def test_approved_teacher_weaken_rule_does_not_reduce_board_apply40(tmp_path: Path) -> None:
    from app.models.enums import PolicyScopeType
    from app.models.policy import PolicyRule
    from app.paper_distribution.mandatory_policy_resolver import PAPER_MANDATORY_POLICY_KEY

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=40.0),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {
        **(inst.metadata_json or {}),
        "board_code": EDUVIJNA_DEMO_BOARD_CODE,
    }
    teacher = ensure_teacher_for_scope(
        session, institution_id=INST_A, external_code="t-weaken-r29"
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    weaken_rule = PolicyRule(
        scope_type=PolicyScopeType.TEACHER.value,
        scope_code=str(teacher.id),
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json={"mandatory_cognitive_exact_percent": {"apply": 20.0}},
        priority=5,
        active=True,
        metadata_json={
            "mandatory_source_locator": FICTITIOUS_BOARD_MANDATORY_LOCATOR,
            "enforcement": "weaken",
        },
    )
    session.add(board_rule)
    session.add(weaken_rule)
    session.flush()
    revision.policy_rules.extend([board_rule, weaken_rule])
    _approve_mandatory_policy_for_rule(
        session,
        rule=board_rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    _approve_mandatory_policy_for_rule(
        session,
        rule=weaken_rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        teacher_id=str(teacher.id),
        organization_id=ctx["organization_id"],
    )
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    ranges = merged.get("mandatory_cognitive_ranges") or []
    assert any(
        isinstance(entry, dict)
        and str(entry.get("key")) == "apply"
        and float(entry.get("exact_percent") or 0) == 40.0
        for entry in ranges
    )
    ensure_paper_target_policy_configured(session)
    apply_paper, apply_trust = _apply_paper_with_day6_bindings(session, ctx, apply_count=4)
    result = evaluate_paper_distribution_with_session(
        session,
        apply_paper,
        day6_trust=apply_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert result.verdict == PaperDistributionVerdict.PASS, result.issue_codes
    assert result.audit_ref


def test_small_paper_infeasible_mandatory_count_not_pass(tmp_path: Path) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    ctx = graph_ctx
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=2),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {
        **(inst.metadata_json or {}),
        "board_code": EDUVIJNA_DEMO_BOARD_CODE,
    }
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)
    bindings: list[PaperDay6ItemBinding] = []
    items: list[PaperItemInput] = []
    for index in range(1):
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"infeasible-{index}",
            paper_marks=1.0,
            declared_cognitive_level="remember",
        )
        bindings.append(
            PaperDay6ItemBinding(
                item_id=str(validated["item_id"]), validation_run_id=run_id
            )
        )
        items.append(_paper_item_from_validated(validated))
    request = PaperDistributionRequest(
        paper_id="infeasible-remember-count",
        items=items,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=100.0)
        ],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    result = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(
            institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
        ),
    )
    assert result.verdict != PaperDistributionVerdict.PASS
    assert result.issue_codes
    assert result.audit_ref


def test_seven_item_reconcile_targets_persisted_audit(tmp_path: Path) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    ensure_paper_target_policy_configured(session)
    levels = ["remember", "understand", "apply", "analyze", "evaluate", "remember", "understand"]
    bindings: list[PaperDay6ItemBinding] = []
    items: list[PaperItemInput] = []
    for index, level in enumerate(levels):
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"seven-item-{index}",
            paper_marks=1.0,
            declared_cognitive_level=level,
        )
        bindings.append(
            PaperDay6ItemBinding(item_id=str(validated["item_id"]), validation_run_id=run_id)
        )
        items.append(_paper_item_from_validated(validated))
    targets = [
        DistributionTarget(dimension="cognitive", key="remember", exact_percent=29.0),
        DistributionTarget(dimension="cognitive", key="understand", exact_percent=29.0),
        DistributionTarget(dimension="cognitive", key="apply", exact_percent=14.0),
        DistributionTarget(dimension="cognitive", key="analyze", exact_percent=14.0),
        DistributionTarget(dimension="cognitive", key="evaluate", exact_percent=14.0),
    ]
    request = PaperDistributionRequest(
        paper_id="seven-item-reconcile",
        items=items,
        cognitive_targets=targets,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    first = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A),
    )
    assert first.verdict == PaperDistributionVerdict.PASS, first.issue_codes
    assert first.audit_ref
    second = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A),
    )
    assert second.audit_ref == first.audit_ref
