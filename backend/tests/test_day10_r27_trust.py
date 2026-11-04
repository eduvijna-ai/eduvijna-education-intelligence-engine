"""Day10 R27 — mapping revoke scope, mandatory evidence binding, paper evaluator matrix."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    approve_mapping_with_curator,
    ensure_mapping_curator_credential,
    issue_mapping_revoke_decision,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    ensure_teacher_for_scope,
    mandatory_board_policy_rule,
    mandatory_institution_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR
from test_day10_r18_trust import _approve_mandatory_policy_for_rule
from test_day10_r20_trust import _apply_paper_with_day6_bindings

from app.common.trust_execution import TrustExecutionMode
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    mandatory_policy_claim_active,
)
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload
from app.paper_distribution.target_policy_registry import ensure_paper_target_policy_configured
from app.prerequisite_intelligence.authority import load_revision_record
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    mapping_claim_authorized_for_overlay,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def _bootstrap_mapping_curator(
    session, ctx: dict[str, str], *, teacher_id: str | None = None
) -> MappingClaimApprovalContext:
    ensure_mapping_curator_registry(session)
    actor_code = (
        DEFAULT_MAPPING_CURATOR_ACTOR
        if not teacher_id
        else f"{DEFAULT_MAPPING_CURATOR_ACTOR}-t-{teacher_id[:8]}"
    )
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_code,
    )
    ensure_mapping_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        teacher_id=teacher_id,
    )
    return MappingClaimApprovalContext(
        actor_id=actor_code,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        teacher_id=teacher_id,
    )


def test_two_teacher_mapping_claims_cross_revoke_blocked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    teacher_a = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-a-r27")
    teacher_b = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-b-r27")
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    ctx_a = _bootstrap_mapping_curator(session, ctx, teacher_id=str(teacher_a.id))
    ctx_b = _bootstrap_mapping_curator(session, ctx, teacher_id=str(teacher_b.id))
    claim_a = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=ctx_a,
    )
    claim_b = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=ctx_b,
    )
    token_a_on_b = issue_mapping_revoke_decision(
        session,
        admin_external_code=ctx_a.actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=ctx_a,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_b,
    )
    with pytest.raises(MappingClaimAuthorityError, match="scope mismatch|not active"):
        revoke_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            claim_id=claim_b,
            actor_id=ctx_a.actor_id,
            curator_decision_token=token_a_on_b,
            approval_context=ctx_a,
        )
    token_a = issue_mapping_revoke_decision(
        session,
        admin_external_code=ctx_a.actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=ctx_a,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_a,
    )
    revoke_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_a,
        actor_id=ctx_a.actor_id,
        curator_decision_token=token_a,
        approval_context=ctx_a,
    )
    still_active_b = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "root_cause_mapping_claim_revoked",
        )
    ).all()
    revoked_ids = {str((e.payload_json or {}).get("claim_id")) for e in still_active_b}
    assert claim_a in revoked_ids
    assert claim_b not in revoked_ids
    record = load_revision_record(session, ctx["source_revision_id"])
    assert record is not None
    mapping_entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert mapping_entry is not None
    overlay_b = {
        "misconception_code": mapping_entry.misconception_code,
        "candidate_concept_codes": list(mapping_entry.candidate_concept_codes),
        "source_locator": _MAPPING_SOURCE_LOCATOR,
        "mapping_registry_version": "root-cause-mapping@v1",
        "organization_id": ctx_b.organization_id,
        "institution_id": ctx_b.institution_id,
        "curriculum_version_id": ctx_b.curriculum_version_id,
        "teacher_id": ctx_b.teacher_id,
    }
    approved_b = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == ctx["source_revision_id"],
            SourceAuditEvent.event_type == "root_cause_mapping_claim_approved",
        )
    ).all()
    b_payload = next(
        (
            e.payload_json
            for e in approved_b
            if str((e.payload_json or {}).get("claim_id")) == claim_b
        ),
        None,
    )
    assert b_payload is not None
    overlay_b["mapping_evidence_checksum"] = b_payload.get("mapping_evidence_checksum")
    overlay_b["source_span_checksum"] = b_payload.get("source_span_checksum")
    graph_scope_b = PrerequisiteGraphScope(
        curriculum_version_id=ctx_b.curriculum_version_id,
        organization_id=ctx_b.organization_id,
        institution_id=ctx_b.institution_id,
        teacher_id=ctx_b.teacher_id,
    )
    assert mapping_claim_authorized_for_overlay(
        session,
        record,
        mapping_entry,
        overlay_b,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope_b,
    )


def test_institution_curator_cannot_revoke_teacher_specific_mapping_claim(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    teacher = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-inst-r27")
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    teacher_ctx = _bootstrap_mapping_curator(session, ctx, teacher_id=str(teacher.id))
    inst_ctx = _bootstrap_mapping_curator(session, ctx, teacher_id=None)
    claim_teacher = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=teacher_ctx,
    )
    token = issue_mapping_revoke_decision(
        session,
        admin_external_code=inst_ctx.actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=inst_ctx,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_teacher,
    )
    with pytest.raises(MappingClaimAuthorityError, match="scope mismatch|not active"):
        revoke_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            claim_id=claim_teacher,
            actor_id=inst_ctx.actor_id,
            curator_decision_token=token,
            approval_context=inst_ctx,
        )


def test_mandatory_claim_inactive_after_post_approval_board_mutation(
    tmp_path: Path,
) -> None:
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
    assert mandatory_policy_claim_active(
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
    revision.source.board_or_exam = "other-board"
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


def test_board_remember_mandatory_precedence_over_weaker_institution_rule(
    tmp_path: Path,
) -> None:
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
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    remember_board = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
        priority=10,
    )
    inst_rule = mandatory_institution_policy_rule(
        institution_id=INST_A,
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 1}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        priority=20,
    )
    session.add(remember_board)
    session.add(inst_rule)
    session.flush()
    revision.policy_rules.extend([remember_board, inst_rule])
    _approve_mandatory_policy_for_rule(
        session,
        rule=remember_board,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="weaken"):
        _approve_mandatory_policy_for_rule(
            session,
            rule=inst_rule,
            revision_id=revision.id,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
        )
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
    )
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    errors = merged.get("mandatory_resolution_errors") or []
    assert not errors
    assert mandatory_policy_claim_active(
        session,
        rule_id=str(remember_board.id),
        revision_id=revision.id,
        scope_type=str(remember_board.scope_type),
        scope_code=str(remember_board.scope_code),
        policy_key=str(remember_board.policy_key),
        value_json=dict(remember_board.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=exec_ctx,
    )
    assert not mandatory_policy_claim_active(
        session,
        rule_id=str(inst_rule.id),
        revision_id=revision.id,
        scope_type=str(inst_rule.scope_type),
        scope_code=str(inst_rule.scope_code),
        policy_key=str(inst_rule.policy_key),
        value_json=dict(inst_rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=exec_ctx,
    )


def test_apply40_mandatory_day6_paper_evaluator_matrix(tmp_path: Path) -> None:
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
    apply_paper, apply_trust = _apply_paper_with_day6_bindings(session, ctx, apply_count=4)
    pass_four = evaluate_paper_distribution_with_session(
        session,
        apply_paper,
        day6_trust=apply_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(
            institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
        ),
    )
    assert pass_four.verdict == PaperDistributionVerdict.PASS, pass_four.issue_codes
    fail_paper, fail_trust = _apply_paper_with_day6_bindings(session, ctx, apply_count=5)
    fail_five = evaluate_paper_distribution_with_session(
        session,
        fail_paper,
        day6_trust=fail_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(
            institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
        ),
    )
    assert fail_five.verdict != PaperDistributionVerdict.PASS
