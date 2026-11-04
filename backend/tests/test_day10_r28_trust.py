"""Day10 R28 — snapshot checksum gate, curator ticket source binding, paper matrix."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mandatory_policy_with_curator,
    ensure_mandatory_policy_curator_credential,
    issue_mandatory_policy_approve_decision,
)
from day10_day6_binding import seed_production_day6_audit
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    mandatory_board_policy_rule,
    mandatory_institution_policy_rule,
)
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR
from test_day10_r18_trust import (
    _approve_mandatory_policy_for_rule,
    _paper_item_from_validated,
)
from test_day10_r20_trust import _apply_paper_with_day6_bindings

from app.common.trust_execution import TrustExecutionMode
from app.curator_auth.issuer import CuratorAuthError
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    _policy_value_checksum,
    _rule_lifecycle_digest,
    approve_mandatory_policy_claim,
    mandatory_policy_claim_active,
)
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)
from app.source_intelligence.approval_fingerprint import (
    verify_revision_stored_source_snapshot_checksum,
)


def test_dual_snapshot_board_tamper_rejects_mandatory_claim_read(tmp_path: Path) -> None:
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
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
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
        execution_context=exec_ctx,
    )
    tampered_board = "eduvijna-tampered-board"
    revision.source.board_or_exam = tampered_board
    snapshot = dict((revision.metadata_json or {}).get("source_snapshot") or {})
    snapshot["board_or_exam"] = tampered_board
    revision.metadata_json = {
        **(revision.metadata_json or {}),
        "source_snapshot": snapshot,
    }
    session.flush()
    assert not verify_revision_stored_source_snapshot_checksum(revision)
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
        execution_context=exec_ctx,
    )


def test_mandatory_ticket_issued_on_source_a_cannot_consume_after_reapproval_b(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    excerpt_a = default_board_mandatory_excerpt(remember_exact_count=2)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=excerpt_a,
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
    actor_id = "founder-day10-trust"
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_id,
    )
    ensure_mandatory_policy_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        board_scope_authorized=True,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    value_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    lifecycle = _rule_lifecycle_digest(rule)
    stale_token = issue_mandatory_policy_approve_decision(
        session,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        rule=rule,
        revision_id=revision.id,
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
    )
    excerpt_b = excerpt_a + " revised mandatory excerpt for ticket binding test."
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        policy_excerpt=excerpt_b,
    )
    with pytest.raises(
        (MandatoryPolicyClaimAuthorityError, CuratorAuthError),
        match="binding mismatch|content integrity|snapshot|source",
    ):
        approve_mandatory_policy_claim(
            session,
            rule_id=str(rule.id),
            revision_id=revision.id,
            scope_type=str(rule.scope_type),
            scope_code=str(rule.scope_code),
            policy_key=str(rule.policy_key),
            value_json=dict(rule.value_json or {}),
            actor_id=actor_id,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curator_decision_token=stale_token,
        )
    approve_mandatory_policy_with_curator(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        actor_id=actor_id,
        policy_curator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )


def test_board_mandatory_precedence_retains_stricter_count_when_compatible(
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
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    inst_rule = mandatory_institution_policy_rule(
        institution_id=INST_A,
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    session.add(board_rule)
    session.add(inst_rule)
    session.flush()
    revision.policy_rules.extend([board_rule, inst_rule])
    _approve_mandatory_policy_for_rule(
        session,
        rule=board_rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
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
    assert not merged.get("mandatory_resolution_errors")
    ranges = merged.get("mandatory_cognitive_ranges") or []
    assert any(
        isinstance(entry, dict)
        and str(entry.get("key")) == "remember"
        and int(entry.get("exact_count") or 0) == 2
        for entry in ranges
    )


def _mark_weighted_apply_paper(
    session,
    ctx: dict[str, str],
    *,
    apply_marks: list[float],
    paper_suffix: str,
) -> tuple[PaperDistributionRequest, PaperDay6TrustContext]:
    """Seed-audit mark-weighted arithmetic only (not genuine Day6 validate_item provenance)."""
    items: list[PaperItemInput] = []
    bindings: list[PaperDay6ItemBinding] = []
    for index, marks in enumerate(apply_marks):
        item_id = f"mark-weight-{paper_suffix}-{index}-{marks}"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=ctx["organization_id"],
            institution_id=INST_A,
            curriculum_version_id=ctx["curriculum_version_id"],
            declared_cognitive_level="apply",
            marks=marks,
        )
        bindings.append(PaperDay6ItemBinding(item_id=item_id, validation_run_id=run_id))
        items.append(_paper_item_from_validated(validated))
    remember_count = max(0, 10 - len(apply_marks))
    for index in range(remember_count):
        item_id = f"mark-weight-{paper_suffix}-remember-{index}"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=ctx["organization_id"],
            institution_id=INST_A,
            curriculum_version_id=ctx["curriculum_version_id"],
            declared_cognitive_level="remember",
        )
        bindings.append(PaperDay6ItemBinding(item_id=item_id, validation_run_id=run_id))
        items.append(_paper_item_from_validated(validated))
    request = PaperDistributionRequest(
        paper_id=f"mark-weight-apply40-{paper_suffix}",
        items=items,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="apply", exact_percent=40.0)
        ],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        include_mark_weighted=True,
    )
    return request, PaperDay6TrustContext.from_item_bindings(bindings)


def test_mark_weighted_apply40_mandatory_pass_and_fail(tmp_path: Path) -> None:
    """Uses seed_production_day6_audit marks aligned with paper items (not real validate_item)."""
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
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A, board_code=EDUVIJNA_DEMO_BOARD_CODE
    )
    pass_paper, pass_trust = _mark_weighted_apply_paper(
        session, ctx, apply_marks=[1.5, 1.0, 1.0, 0.5], paper_suffix="pass"
    )
    pass_result = evaluate_paper_distribution_with_session(
        session,
        pass_paper,
        day6_trust=pass_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert pass_result.verdict == PaperDistributionVerdict.PASS, pass_result.issue_codes
    fail_paper, fail_trust = _mark_weighted_apply_paper(
        session, ctx, apply_marks=[2.0, 1.5, 1.0, 1.5], paper_suffix="fail"
    )
    fail_result = evaluate_paper_distribution_with_session(
        session,
        fail_paper,
        day6_trust=fail_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert fail_result.verdict != PaperDistributionVerdict.PASS


def test_teacher_weaken_rule_does_not_reduce_board_apply_mandatory(tmp_path: Path) -> None:
    from day10_source_lifecycle import ensure_teacher_for_scope

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
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    from app.models.enums import PolicyScopeType
    from app.models.policy import PolicyRule
    from app.paper_distribution.mandatory_policy_resolver import PAPER_MANDATORY_POLICY_KEY

    teacher = ensure_teacher_for_scope(
        session, institution_id=INST_A, external_code="teacher-weaken-r28"
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


def test_mapping_ticket_rejects_stale_source_after_content_reapproval(tmp_path: Path) -> None:
    from day10_curator_auth import (
        DEFAULT_MAPPING_CURATOR_SECRET,
        issue_mapping_approve_decision,
    )
    from test_day10_r27_trust import _bootstrap_mapping_curator

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping

    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = _bootstrap_mapping_curator(session, ctx)
    stale = issue_mapping_approve_decision(
        session,
        admin_external_code=approval_ctx.actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
    )
    ensure_genuine_source_content_approval(
        session,
        tmp_path,
        ctx["source_revision_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
        manual_metadata={
            "document_type": "official_misconception_mapping_table",
            "locator": _MAPPING_SOURCE_LOCATOR,
            "excerpt": "Revised mapping excerpt for R28 ticket binding test.",
        },
    )
    from app.root_cause_intelligence.mapping_claim_authority import (
        MappingClaimAuthorityError,
        approve_root_cause_mapping_claim,
    )

    with pytest.raises(
        (MappingClaimAuthorityError, CuratorAuthError),
        match="binding mismatch|snapshot|integrity|source",
    ):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=approval_ctx,
            curator_decision_token=stale,
        )
