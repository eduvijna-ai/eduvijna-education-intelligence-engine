"""Day10 R35 — canonical envelope identity, per-claim retirement, deleted rule."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    ensure_mandatory_policy_curator_credential,
    issue_curator_write_decision,
)
from day10_source_lifecycle import EDUVIJNA_DEMO_BOARD_CODE
from sqlalchemy import delete, select
from test_day10_r8_trust import _seed_production_institution_graph, _session
from test_day10_r18_trust import MANDATORY_BOARD_POLICY_ACTOR, _approve_mandatory_policy_for_rule
from test_day10_r31_trust import _seed_board_apply40
from test_day10_r32_trust import _evaluate_apply_paper, _exec_ctx
from test_day10_r34_trust import _board_rule

from app.curator_auth.issuer import CuratorScope
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, policy_rule_source_revisions
from app.models.tenancy import AdminActor
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.mandatory_policy_claim_authority import (
    MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
    mandatory_policy_revoke_binding_payload,
    revoke_and_retire_mandatory_policy_rule,
)
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload


def _first_approve_event(session) -> SourceAuditEvent:
    event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).first()
    assert event is not None
    return event


def _mutate_approve_top_level(session, event: SourceAuditEvent, **fields: object) -> None:
    payload = dict(event.payload_json or {})
    payload.update(fields)
    event.payload_json = payload
    session.flush()


def _assert_mandatory_auth_unavailable(session, ctx: dict[str, str]) -> None:
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    errors = merged.get("mandatory_resolution_errors") or []
    assert any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in errors
    )


def _second_signed_claim_same_rule(session, ctx: dict[str, str], rule: PolicyRule) -> None:
    rule.metadata_json = {
        **(rule.metadata_json or {}),
        "r35_second_approval_seq": "1",
    }
    session.flush()
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=ctx["source_revision_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    rule.metadata_json = {
        k: v for k, v in (rule.metadata_json or {}).items() if k != "r35_second_approval_seq"
    }
    session.flush()


def _claim_ids_for_rule(session, rule_id: str) -> list[str]:
    claim_ids: list[str] = []
    for event in session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).all():
        payload = event.payload_json or {}
        approval = payload.get("curator_approval") or {}
        claim = approval.get("claim") if isinstance(approval, dict) else {}
        identity = claim if isinstance(claim, dict) else payload
        if str(identity.get("policy_rule_id") or payload.get("policy_rule_id") or "") == rule_id:
            cid = str(identity.get("claim_id") or payload.get("claim_id") or "")
            if cid and cid not in claim_ids:
                claim_ids.append(cid)
    assert len(claim_ids) >= 1
    return claim_ids


def test_top_level_scope_code_tamper_still_enforces_mandate(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    event = _first_approve_event(session)
    _mutate_approve_top_level(session, event, scope_code="other-board")
    _assert_mandatory_auth_unavailable(session, ctx)
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r35-scope-tamper")
    assert result.verdict != PaperDistributionVerdict.PASS


def test_top_level_policy_key_tamper_still_enforces_mandate(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    event = _first_approve_event(session)
    _mutate_approve_top_level(session, event, policy_key="paper-distribution-other")
    _assert_mandatory_auth_unavailable(session, ctx)


def test_top_level_effective_to_tamper_still_enforces_mandate(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    event = _first_approve_event(session)
    _mutate_approve_top_level(
        session,
        event,
        effective_to=(date.today() - timedelta(days=30)).isoformat(),
    )
    _assert_mandatory_auth_unavailable(session, ctx)
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r35-eff-to")
    assert result.verdict != PaperDistributionVerdict.PASS


def test_untampered_compliant_paper_still_passes(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=4, id_prefix="r35-pass")
    assert result.verdict == PaperDistributionVerdict.PASS


def test_partial_rule_retirement_leaves_second_claim_enforced(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    claim_ids = _claim_ids_for_rule(session, str(rule.id))
    assert len(claim_ids) >= 1
    first_claim = claim_ids[0]
    if len(claim_ids) < 2:
        _second_signed_claim_same_rule(session, ctx, rule)
        claim_ids = _claim_ids_for_rule(session, str(rule.id))
    assert len(claim_ids) >= 2
    first_claim, second_claim = claim_ids[0], claim_ids[1]
    assert first_claim != second_claim

    session.commit()
    _, fail_before = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r35-two-claims")
    assert fail_before.verdict != PaperDistributionVerdict.PASS

    admin = session.scalar(
        select(AdminActor).where(AdminActor.external_code == MANDATORY_BOARD_POLICY_ACTOR)
    )
    assert admin is not None
    ensure_mandatory_policy_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        board_code=EDUVIJNA_DEMO_BOARD_CODE,
        board_scope_authorized=True,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    retire_token = issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id),
            revision_id=ctx["source_revision_id"],
            claim_id=first_claim,
            retire_rule=True,
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code=EDUVIJNA_DEMO_BOARD_CODE,
        ),
    )
    revoke_and_retire_mandatory_policy_rule(
        session,
        rule_id=str(rule.id),
        revision_id=ctx["source_revision_id"],
        claim_id=first_claim,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=retire_token,
    )
    session.flush()
    assert rule.active is False

    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    errors = merged.get("mandatory_resolution_errors") or []
    assert any(str(item).startswith("mandatory_policy.retirement_unauthorized:") for item in errors)
    session.commit()
    _, fail_after = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r35-one-retired")
    assert fail_after.verdict != PaperDistributionVerdict.PASS

    # Retire the remaining claim explicitly.
    second_rev = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).all()
    rev_id_for_second = ctx["source_revision_id"]
    for ev in second_rev:
        payload = ev.payload_json or {}
        cid = str(payload.get("claim_id") or "")
        if cid == second_claim:
            rev_id_for_second = str(ev.source_revision_id or ctx["source_revision_id"])
            break
    retire_b = issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id),
            revision_id=rev_id_for_second,
            claim_id=second_claim,
            retire_rule=True,
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code=EDUVIJNA_DEMO_BOARD_CODE,
        ),
    )
    revoke_and_retire_mandatory_policy_rule(
        session,
        rule_id=str(rule.id),
        revision_id=rev_id_for_second,
        claim_id=second_claim,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=retire_b,
    )
    session.flush()
    merged_after = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    assert not (merged_after.get("mandatory_resolution_errors") or [])


def test_deleted_rule_with_signed_approval_blocks_noncompliant_paper(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    rule_id = str(rule.id)
    session.commit()

    session.execute(
        delete(policy_rule_source_revisions).where(
            policy_rule_source_revisions.c.policy_rule_id == rule.id
        )
    )
    session.delete(rule)
    session.flush()
    assert session.get(PolicyRule, rule_id) is None

    _assert_mandatory_auth_unavailable(session, ctx)
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r35-deleted-rule")
    assert result.verdict != PaperDistributionVerdict.PASS
