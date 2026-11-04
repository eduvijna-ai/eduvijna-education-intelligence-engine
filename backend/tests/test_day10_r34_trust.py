"""Day10 R34 — plain revoke fail-closed, historic scope, damaged approval lineage."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    ensure_mandatory_policy_curator_credential,
    issue_curator_write_decision,
)
from day10_source_lifecycle import EDUVIJNA_DEMO_BOARD_CODE
from sqlalchemy import select
from test_day10_r8_trust import _seed_production_institution_graph, _session
from test_day10_r18_trust import MANDATORY_BOARD_POLICY_ACTOR
from test_day10_r31_trust import _seed_board_apply40
from test_day10_r32_trust import _evaluate_apply_paper, _exec_ctx

from app.curator_auth.issuer import CuratorScope
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent
from app.models.tenancy import AdminActor
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.mandatory_policy_claim_authority import (
    MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
    mandatory_policy_revoke_binding_payload,
    revoke_and_retire_mandatory_policy_rule,
    revoke_mandatory_policy_claim,
)
from app.paper_distribution.mandatory_policy_resolver import (
    PAPER_MANDATORY_POLICY_KEY,
    merge_scoped_mandatory_policy_payload,
)


def _board_rule(session) -> PolicyRule:
    rule = session.scalars(
        select(PolicyRule).where(
            PolicyRule.policy_key == PAPER_MANDATORY_POLICY_KEY,
            PolicyRule.active.is_(True),
        )
    ).first()
    assert rule is not None
    return rule


def _real_claim_id(session, rule_id: str) -> str:
    for event in session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).all():
        payload = event.payload_json or {}
        if str(payload.get("policy_rule_id") or "") == rule_id:
            return str(payload.get("claim_id") or "")
    raise AssertionError("missing approve event")


def _issue_plain_revoke_token(session, ctx: dict[str, str], rule: PolicyRule, claim_id: str) -> str:
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
    return issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id),
            revision_id=ctx["source_revision_id"],
            claim_id=claim_id,
            retire_rule=False,
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code=EDUVIJNA_DEMO_BOARD_CODE,
        ),
    )


def test_plain_revoke_while_rule_active_fails_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    claim_id = _real_claim_id(session, str(rule.id))
    session.commit()
    assert rule.active is True
    revoke_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=_issue_plain_revoke_token(session, ctx, rule, claim_id),
    )
    session.flush()
    assert rule.active is True
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    prefix = "mandatory_policy.authorization_unavailable:"
    errors = merged.get("mandatory_resolution_errors") or []
    assert any(str(item).startswith(prefix) for item in errors)
    session.commit()
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r34-plain-revoke")
    assert result.verdict != PaperDistributionVerdict.PASS


def test_scope_code_mutation_still_enforces_historic_mandate(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    rule.scope_code = "other-board"
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in (merged.get("mandatory_resolution_errors") or [])
    )


def test_retroactive_effective_to_on_rule_still_enforces_signed_dates(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    rule.effective_to = date.today() - timedelta(days=1)
    session.flush()
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    assert any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in (merged.get("mandatory_resolution_errors") or [])
    )


def test_damaged_approval_audit_still_fails_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    approve = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).first()
    assert approve is not None
    approve.actor_id = None
    session.flush()
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    assert any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in (merged.get("mandatory_resolution_errors") or [])
    )


def test_signed_revoke_and_retire_clears_mandatory_obligation(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    claim_id = _real_claim_id(session, str(rule.id))
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
            claim_id=claim_id,
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
        claim_id=claim_id,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=retire_token,
    )
    session.commit()
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    assert not merged.get("mandatory_resolution_errors")
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r34-retired")
    assert result.verdict == PaperDistributionVerdict.PASS
