"""Day10 R30 — curator grants, mark-weighted provenance, weaken, revoke actor."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mapping_with_curator,
    ensure_mandatory_policy_curator_credential,
    issue_mandatory_policy_approve_decision,
    issue_mapping_revoke_decision,
)
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_teacher_for_scope,
    mandatory_board_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR
from test_day10_r18_trust import (
    MANDATORY_BOARD_POLICY_ACTOR,
    _approve_mandatory_policy_for_rule,
    _bootstrap_mapping_curator,
    _paper_item_from_validated,
)
from test_day10_r29_trust import _persist_real_day6_item

from app.common.trust_execution import TrustExecutionMode
from app.curator_auth.issuer import (
    CuratorAuthError,
    CuratorScope,
    issue_curator_write_decision,
    verify_durable_curator_approval,
)
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.models.education_intelligence import ValidationAuditRun
from app.models.enums import PolicyScopeType
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import PaperDistributionIssueCode, PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    _policy_value_checksum,
    _rule_lifecycle_digest,
    mandatory_policy_claim_active,
    mandatory_policy_claim_id,
    mandatory_policy_revoke_binding_payload,
    revoke_mandatory_policy_claim,
)
from app.paper_distribution.mandatory_policy_resolver import PAPER_MANDATORY_POLICY_KEY
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
    mapping_revoke_binding_payload,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_teacher_credential_cannot_issue_board_mandatory_approve(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=40.0),
    )
    teacher = ensure_teacher_for_scope(
        session, institution_id=INST_A, external_code="t-r30-escalation"
    )
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(board_rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(board_rule)
    teacher_admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=f"founder-day10-mandatory-teacher-{teacher.id}",
    )
    ensure_mandatory_policy_curator_credential(
        session,
        teacher_admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        teacher_id=str(teacher.id),
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    value_checksum = _policy_value_checksum(dict(board_rule.value_json or {}))
    lifecycle = _rule_lifecycle_digest(board_rule)
    with pytest.raises(CuratorAuthError):
        issue_mandatory_policy_approve_decision(
            session,
            admin_external_code=teacher_admin.external_code,
            operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            rule=board_rule,
            revision_id=revision.id,
            value_checksum=value_checksum,
            rule_lifecycle_digest=lifecycle,
        )


def test_board_and_teacher_mandatory_grants_stay_independent(tmp_path: Path) -> None:
    from app.paper_distribution.mandatory_policy_resolver import (
        merge_scoped_mandatory_policy_payload,
    )

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
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": EDUVIJNA_DEMO_BOARD_CODE}
    teacher = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-r30-split")
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
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="weakening"):
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
    assert mandatory_policy_claim_active(
        session,
        rule_id=str(board_rule.id),
        revision_id=revision.id,
        scope_type=str(board_rule.scope_type),
        scope_code=str(board_rule.scope_code),
        policy_key=str(board_rule.policy_key),
        value_json=dict(board_rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=exec_ctx,
    )
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    ranges = merged.get("mandatory_cognitive_ranges") or []
    assert any(
        isinstance(entry, dict)
        and str(entry.get("key")) == "apply"
        and float(entry.get("exact_percent") or 0) == 40.0
        for entry in ranges
    )


def test_mark_weighted_rejects_day6_pass_without_validated_marks(tmp_path: Path) -> None:
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
    item = positive_cbse_item(day6_ctx).model_copy(update={"item_id": "no-marks-day6"})
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(
        item,
        board_code="cbse",
        persist=True,
        actor_id="founder-day10-trust",
        trusted_scope={
            "organization_id": day6_ctx["organization_id"],
            "institution_id": INST_A,
            "curriculum_version_id": day6_ctx["curriculum_version_id"],
        },
    )
    assert not summary.blocking_failure
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    assert validated.get("marks") is None
    bindings = [
        PaperDay6ItemBinding(
            item_id=str(validated["item_id"]),
            validation_run_id=str(record.id),
        )
    ]
    forged_items = [
        PaperItemInput(
            item_id=str(validated["item_id"]),
            marks=5.0,
            cognitive_level=str(validated.get("declared_cognitive_level")),
            competency_codes=list(validated.get("competency_codes") or []),
            day6_validated=True,
            metadata_json={
                "day6_input_hash": validated.get("input_hash"),
                "curriculum_version_id": validated.get("curriculum_version_id"),
                "grade_year_code": validated.get("grade_year_code"),
                "medium_code": validated.get("medium_code"),
                "subject_code": validated.get("subject_code"),
                "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
            },
        )
    ]
    result = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="forged-marks-no-day6-marks",
            items=forged_items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A),
    )
    assert result.verdict != PaperDistributionVerdict.PASS
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_count_only_production_ok_without_validated_marks_when_not_mark_weighted(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    ensure_paper_target_policy_configured(session)
    item = positive_cbse_item(day6_ctx).model_copy(update={"item_id": "count-only"})
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(item, board_code="cbse", persist=True, actor_id="actor")
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    paper_item = _paper_item_from_validated(validated)
    result = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="count-only-no-weight",
            items=[paper_item],
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=False,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(
            [
                PaperDay6ItemBinding(
                    item_id=str(validated["item_id"]),
                    validation_run_id=str(record.id),
                )
            ]
        ),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert result.verdict == PaperDistributionVerdict.PASS


def test_mapping_revoke_durable_verify_fails_when_actor_cleared(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
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
    revoke_token = issue_mapping_revoke_decision(
        session,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
    )
    revoke_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
        actor_id=actor_id,
        curator_decision_token=revoke_token,
        approval_context=approval_ctx,
    )
    revoke_event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "root_cause_mapping_claim_revoked",
        )
    ).first()
    assert revoke_event is not None
    binding = mapping_revoke_binding_payload(
        revision_id=ctx["source_revision_id"], claim_id=claim_id
    )
    assert verify_durable_curator_approval(
        session,
        revoke_event.payload_json or {},
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_REVOKE,
        binding_payload=binding,
        source_audit_event_id=revoke_event.id,
        audit_actor_id=str(revoke_event.actor_id or ""),
    )
    revoke_event.actor_id = None
    session.flush()
    assert not verify_durable_curator_approval(
        session,
        revoke_event.payload_json or {},
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_REVOKE,
        binding_payload=binding,
        source_audit_event_id=revoke_event.id,
        audit_actor_id="",
    )


def test_mandatory_policy_revoke_durable_verify_fails_when_actor_cleared(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=1),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": EDUVIJNA_DEMO_BOARD_CODE}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 1}]},
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
    lifecycle = _rule_lifecycle_digest(rule)
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=str(rule.id),
        source_revision_id=revision.id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_checksum=_policy_value_checksum(dict(rule.value_json or {})),
        rule_lifecycle_digest=lifecycle,
    )
    revoke_token = issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id), revision_id=revision.id, claim_id=claim_id
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code=EDUVIJNA_DEMO_BOARD_CODE,
        ),
    )
    revoke_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=revision.id,
        claim_id=claim_id,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=revoke_token,
    )
    revoke_event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "paper_mandatory_policy_claim_revoked",
        )
    ).first()
    assert revoke_event is not None
    revoke_binding = mandatory_policy_revoke_binding_payload(
        rule_id=str(rule.id), revision_id=revision.id, claim_id=claim_id
    )
    assert verify_durable_curator_approval(
        session,
        revoke_event.payload_json or {},
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=revoke_binding,
        source_audit_event_id=revoke_event.id,
        audit_actor_id=str(revoke_event.actor_id or ""),
    )
    revoke_event.actor_id = None
    session.flush()
    assert not verify_durable_curator_approval(
        session,
        revoke_event.payload_json or {},
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=revoke_binding,
        source_audit_event_id=revoke_event.id,
        audit_actor_id="",
    )


def test_real_day6_unequal_marks_mark_weighted_policy(tmp_path: Path) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        graph_ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=40.0),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": EDUVIJNA_DEMO_BOARD_CODE}
    revision = session.get(SourceRevision, graph_ctx["source_revision_id"])
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
        organization_id=graph_ctx["organization_id"],
        institution_id=graph_ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)
    bindings: list[PaperDay6ItemBinding] = []
    items: list[PaperItemInput] = []
    mark_plan = [1.0] * 10
    for index, marks in enumerate(mark_plan):
        level = "apply" if index < 4 else "remember"
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"r30-marks-{index}",
            paper_marks=marks,
            declared_cognitive_level=level,
        )
        bindings.append(
            PaperDay6ItemBinding(item_id=str(validated["item_id"]), validation_run_id=run_id)
        )
        items.append(_paper_item_from_validated(validated))
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        organization_id=graph_ctx["organization_id"],
    )
    ok = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r30-real-marks-pass",
            items=items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert ok.verdict == PaperDistributionVerdict.PASS, ok.issue_codes
    tampered = [items[0].model_copy(update={"marks": 99.0}), *items[1:]]
    bad = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r30-real-marks-tamper",
            items=tampered,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in bad.issue_codes
