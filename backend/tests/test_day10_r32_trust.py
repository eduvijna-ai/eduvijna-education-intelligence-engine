"""Day10 R32 — mandatory authorization fail-closed + inactive parent organization."""

from __future__ import annotations

from pathlib import Path

from day10_day6_binding import seed_production_day6_audit
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    mandatory_board_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, ORG_A, _seed_production_institution_graph, _session
from test_day10_r18_trust import _paper_item_from_validated
from test_day10_r31_trust import _seed_board_apply40

from app.common.trust_execution import TrustExecutionMode
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Organization
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import (
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
    mandatory_policy_claim_active,
)
from app.paper_distribution.mandatory_policy_resolver import (
    PAPER_MANDATORY_POLICY_KEY,
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    paper_targets_authorized,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)
from app.source_intelligence.approval_fingerprint import (
    verify_revision_stored_source_snapshot_checksum,
)


def _apply_paper(
    session,
    ctx: dict[str, str],
    *,
    apply_count: int,
    id_prefix: str = "board-apply40",
) -> tuple[PaperDistributionRequest, PaperDay6TrustContext]:
    items: list[PaperItemInput] = []
    bindings: list[PaperDay6ItemBinding] = []
    cognitive_levels = ["apply"] * apply_count + ["remember"] * (10 - apply_count)
    for index, level in enumerate(cognitive_levels):
        item_id = f"{id_prefix}-{apply_count}-{index}"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=ctx["organization_id"],
            institution_id=INST_A,
            curriculum_version_id=ctx["curriculum_version_id"],
            declared_cognitive_level=level,
        )
        bindings.append(PaperDay6ItemBinding(item_id=item_id, validation_run_id=run_id))
        items.append(_paper_item_from_validated(validated))
    request = PaperDistributionRequest(
        paper_id=f"{id_prefix}-{apply_count}",
        items=items,
        cognitive_targets=[],
        competency_targets=[],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    return request, PaperDay6TrustContext.from_item_bindings(bindings)


def _exec_ctx(ctx: dict[str, str]) -> PaperExecutionContext:
    return PaperExecutionContext(
        institution_id=INST_A,
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        organization_id=ctx["organization_id"],
    )


def _evaluate_apply_paper(
    session,
    ctx: dict[str, str],
    *,
    apply_count: int,
    id_prefix: str = "board-apply40",
) -> tuple:
    ensure_paper_target_policy_configured(session)
    paper, trust = _apply_paper(
        session, ctx, apply_count=apply_count, id_prefix=id_prefix
    )
    exec_ctx = _exec_ctx(ctx)
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    return paper, result


def test_mandatory_apply40_pass_and_fail_with_valid_authorization(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    session.commit()

    _, pass_result = _evaluate_apply_paper(session, ctx, apply_count=4)
    assert pass_result.verdict == PaperDistributionVerdict.PASS, pass_result.issue_codes
    assert pass_result.audit_ref

    _, fail_result = _evaluate_apply_paper(session, ctx, apply_count=5)
    assert fail_result.verdict != PaperDistributionVerdict.PASS


def test_tampered_mandatory_source_fails_closed_not_silent_pass(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = session.scalars(
        select(PolicyRule).where(
            PolicyRule.policy_key == PAPER_MANDATORY_POLICY_KEY,
            PolicyRule.active.is_(True),
        )
    ).first()
    assert board_rule is not None
    exec_ctx = _exec_ctx(ctx)
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

    tampered_board = "eduvijna-tampered-board-r32"
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
    errors = merged.get("mandatory_resolution_errors") or []
    prefix = "mandatory_policy.authorization_unavailable:"
    assert any(str(item).startswith(prefix) for item in errors)

    session.commit()
    _, fail_result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r32-tamper")
    assert fail_result.verdict == PaperDistributionVerdict.FAIL
    assert PaperDistributionIssueCode.TARGET_INFEASIBLE in fail_result.issue_codes


def test_unsigned_draft_mandatory_rule_does_not_block_valid_paper(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    draft = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 99.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(draft)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(draft)
    session.add(
        SourceAuditEvent(
            source_id=revision.source_id,
            source_revision_id=revision.id,
            event_type=MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            actor_id="forged-unsigned",
            request_id="r32-forged",
            outcome="success",
            payload_json={
                "policy_rule_id": draft.id,
                "claim_id": "forged-claim-no-durable",
            },
        )
    )
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert not any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in (merged.get("mandatory_resolution_errors") or [])
    )
    session.commit()
    _, pass_result = _evaluate_apply_paper(session, ctx, apply_count=4)
    assert pass_result.verdict == PaperDistributionVerdict.PASS


def test_deactivated_mandatory_rule_retires_obligation(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    board_rule = session.scalars(
        select(PolicyRule).where(
            PolicyRule.policy_key == PAPER_MANDATORY_POLICY_KEY,
            PolicyRule.active.is_(True),
        )
    ).first()
    assert board_rule is not None
    board_rule.active = False
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert not merged.get("mandatory_resolution_errors")
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5)
    assert result.verdict == PaperDistributionVerdict.PASS


def test_inactive_parent_organization_fails_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    org = session.get(Organization, ORG_A)
    assert org is not None
    org.active = False
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert "execution_context.organization_id" in (merged.get("mandatory_resolution_errors") or [])

    session.commit()
    paper, trust = _apply_paper(session, ctx, apply_count=4, id_prefix="r32-inactive")
    ensure_paper_target_policy_configured(session)
    ok, path = paper_targets_authorized(
        session,
        paper,
        version=PAPER_TARGET_POLICY_VERSION,
        execution_context=exec_ctx,
    )
    assert not ok
    assert path == "execution_context.organization_id"

    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=exec_ctx,
    )
    assert result.verdict != PaperDistributionVerdict.PASS
    assert result.audit_ref is None

    org.active = True
    session.flush()
    session.commit()
    _, restored = _evaluate_apply_paper(
        session, ctx, apply_count=4, id_prefix="r32-restored"
    )
    assert restored.verdict == PaperDistributionVerdict.PASS
