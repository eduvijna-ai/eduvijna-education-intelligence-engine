"""Day10 R31 — production tenant scope, unequal Day6 marks, mandatory weaken rejection."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_teacher_for_scope,
    mandatory_board_policy_rule,
)
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r18_trust import _approve_mandatory_policy_for_rule, _paper_item_from_validated
from test_day10_r29_trust import _persist_real_day6_item

from app.common.trust_execution import TrustExecutionMode
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.models.enums import PolicyScopeType
from app.models.policy import PolicyRule
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import (
    DistributionDimensionStatus,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
)
from app.paper_distribution.mandatory_policy_resolver import (
    PAPER_MANDATORY_POLICY_KEY,
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)


def _seed_board_apply40(
    session,
    tmp_path: Path,
    ctx: dict[str, str],
) -> None:
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
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(board_rule)
    session.flush()
    revision.policy_rules.append(board_rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=board_rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )


def _ten_item_apply_paper(
    session,
    day6_ctx: dict[str, str],
    *,
    apply_marks: list[float],
    remember_marks: list[float],
) -> tuple[list[PaperDay6ItemBinding], list[PaperItemInput]]:
    assert len(apply_marks) == 4 and len(remember_marks) == 6
    bindings: list[PaperDay6ItemBinding] = []
    items = []
    for index, marks in enumerate(apply_marks):
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"r31-apply-{index}",
            paper_marks=marks,
            declared_cognitive_level="apply",
        )
        bindings.append(
            PaperDay6ItemBinding(item_id=str(validated["item_id"]), validation_run_id=run_id)
        )
        items.append(_paper_item_from_validated(validated))
    for index, marks in enumerate(remember_marks):
        run_id, validated = _persist_real_day6_item(
            session,
            day6_ctx,
            f"r31-remember-{index}",
            paper_marks=marks,
            declared_cognitive_level="remember",
        )
        bindings.append(
            PaperDay6ItemBinding(item_id=str(validated["item_id"]), validation_run_id=run_id)
        )
        items.append(_paper_item_from_validated(validated))
    return bindings, items


def test_production_empty_execution_context_cannot_pass_mandatory_paper(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    _seed_board_apply40(session, tmp_path, graph_ctx)
    ensure_paper_target_policy_configured(session)
    apply_marks = [0.5, 1.0, 1.5, 2.0]
    remember_marks = [1.0, 1.0, 1.5, 1.5, 1.0, 1.5]
    bindings, items = _ten_item_apply_paper(
        session, day6_ctx, apply_marks=apply_marks, remember_marks=remember_marks
    )
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        organization_id=graph_ctx["organization_id"],
    )
    scoped = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r31-scoped-pass",
            items=items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert scoped.verdict == PaperDistributionVerdict.PASS, scoped.issue_codes
    assert scoped.audit_ref
    empty_ctx = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r31-empty-ctx",
            items=items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert empty_ctx.verdict != PaperDistributionVerdict.PASS
    assert empty_ctx.audit_ref is None
    merged = merge_scoped_mandatory_policy_payload(session, {}, PaperExecutionContext())
    assert "mandatory_resolution_errors" in merged


def test_real_day6_unequal_marks_mark_weighted_apply40(tmp_path: Path) -> None:
    session = _session(tmp_path)
    graph_ctx = _seed_production_institution_graph(session)
    day6_ctx = seed_cbse_fixture_curriculum(session)
    day6_ctx.update(
        {
            "organization_id": graph_ctx["organization_id"],
            "institution_id": graph_ctx["institution_id"],
        }
    )
    _seed_board_apply40(session, tmp_path, graph_ctx)
    ensure_paper_target_policy_configured(session)
    exec_ctx = PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        organization_id=graph_ctx["organization_id"],
    )
    pass_apply = [0.5, 1.0, 1.5, 2.0]
    pass_remember = [1.0, 1.0, 1.5, 1.5, 1.0, 1.5]
    bindings, items = _ten_item_apply_paper(
        session, day6_ctx, apply_marks=pass_apply, remember_marks=pass_remember
    )
    ok = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r31-unequal-pass",
            items=items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert ok.verdict == PaperDistributionVerdict.PASS, ok.issue_codes
    assert ok.cognitive_summary.count_percent.get("apply") == pytest.approx(40.0, abs=0.01)
    assert ok.cognitive_summary.mark_weighted_percent.get("apply") == pytest.approx(
        40.0, abs=0.01
    )
    skew_apply = [0.5, 1.0, 1.5, 2.0]
    skew_remember = [0.5] * 6
    skew_bindings, skew_items = _ten_item_apply_paper(
        session, day6_ctx, apply_marks=skew_apply, remember_marks=skew_remember
    )
    skewed = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r31-count-mark-disagreement",
            items=skew_items,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(skew_bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert skewed.verdict != PaperDistributionVerdict.PASS
    assert (
        PaperDistributionIssueCode.COUNT_MARK_DISAGREEMENT in skewed.issue_codes
        or skewed.cognitive_summary.status == DistributionDimensionStatus.FAIL
    )
    tampered = [items[0].model_copy(update={"marks": 99.0}), *items[1:]]
    bad = evaluate_paper_distribution_with_session(
        session,
        PaperDistributionRequest(
            paper_id="r31-tamper",
            items=tampered,
            target_policy_version=PAPER_TARGET_POLICY_VERSION,
            include_mark_weighted=True,
        ),
        day6_trust=PaperDay6TrustContext.from_item_bindings(bindings),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in bad.issue_codes


def test_teacher_lower_apply_without_weaken_flag_rejected_at_approval(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    teacher = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-r31-lower")
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    lower_rule = PolicyRule(
        scope_type=PolicyScopeType.TEACHER.value,
        scope_code=str(teacher.id),
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json={"mandatory_cognitive_exact_percent": {"apply": 20.0}},
        priority=5,
        active=True,
        metadata_json={"mandatory_source_locator": FICTITIOUS_BOARD_MANDATORY_LOCATOR},
    )
    session.add(lower_rule)
    session.flush()
    revision.policy_rules.append(lower_rule)
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="weaken"):
        _approve_mandatory_policy_for_rule(
            session,
            rule=lower_rule,
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
    exact = (merged.get("mandatory_cognitive_exact_percent") or {}).get("apply")
    assert exact == 40.0 or any(
        isinstance(entry, dict)
        and str(entry.get("key")) == "apply"
        and float(entry.get("exact_percent") or 0) == 40.0
        for entry in ranges
    )
