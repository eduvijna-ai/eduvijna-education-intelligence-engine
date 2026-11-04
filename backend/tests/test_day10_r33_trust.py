"""Day10 R33 — mandatory approval history, forged lineage, signed retirement."""

from __future__ import annotations

from pathlib import Path

from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    ensure_mandatory_policy_curator_credential,
    issue_curator_write_decision,
)
from day10_source_lifecycle import (
    EDUVIJNA_DEMO_BOARD_CODE,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    mandatory_board_policy_rule,
)
from sqlalchemy import delete, select
from test_day10_r8_trust import _seed_production_institution_graph, _session
from test_day10_r18_trust import MANDATORY_BOARD_POLICY_ACTOR
from test_day10_r31_trust import _seed_board_apply40
from test_day10_r32_trust import _evaluate_apply_paper, _exec_ctx

from app.curator_auth.issuer import CuratorScope
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision, policy_rule_source_revisions
from app.models.tenancy import AdminActor
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.mandatory_policy_claim_authority import (
    MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
    mandatory_policy_revoke_binding_payload,
    revoke_and_retire_mandatory_policy_rule,
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
    raise AssertionError("expected signed mandatory approval event")


def test_mutated_mandatory_value_keeps_historic_obligation_fail_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    session.commit()

    _, fail_before = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r33-mut-fail")
    assert fail_before.verdict != PaperDistributionVerdict.PASS

    rule.value_json = {"mandatory_cognitive_exact_percent": {"apply": 20.0}}
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    prefix = "mandatory_policy.authorization_unavailable:"
    errors = merged.get("mandatory_resolution_errors") or []
    assert any(str(item).startswith(prefix) for item in errors)

    session.commit()
    _, fail_after = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r33-mut-after")
    assert fail_after.verdict != PaperDistributionVerdict.PASS

    rule.value_json = {"mandatory_cognitive_exact_percent": {"apply": 40.0}}
    session.flush()
    session.commit()
    _, pass_after = _evaluate_apply_paper(session, ctx, apply_count=4, id_prefix="r33-mut-restore")
    assert pass_after.verdict == PaperDistributionVerdict.PASS


def test_detached_revision_link_still_blocks_unsigned_mandatory_change(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    session.execute(
        delete(policy_rule_source_revisions).where(
            policy_rule_source_revisions.c.policy_rule_id == rule.id
        )
    )
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    assert any(
        str(item).startswith("mandatory_policy.authorization_unavailable:")
        for item in (merged.get("mandatory_resolution_errors") or [])
    )


def test_forged_mandatory_event_with_copied_claim_id_does_not_dos(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    approved_rule = _board_rule(session)
    real_claim = _real_claim_id(session, str(approved_rule.id))
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    draft = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 99.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code=EDUVIJNA_DEMO_BOARD_CODE,
    )
    session.add(draft)
    session.flush()
    revision.policy_rules.append(draft)
    session.add(
        SourceAuditEvent(
            source_id=revision.source_id,
            source_revision_id=revision.id,
            event_type=MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            actor_id="forged-copy-claim",
            request_id="r33-forged-copy",
            outcome="success",
            payload_json={
                "policy_rule_id": draft.id,
                "claim_id": real_claim,
                "scope_type": draft.scope_type,
                "scope_code": draft.scope_code,
                "policy_key": draft.policy_key,
                "value_checksum": "deadbeef",
                "rule_lifecycle_digest": "deadbeef",
            },
        )
    )
    session.flush()
    exec_ctx = _exec_ctx(ctx)
    merged = merge_scoped_mandatory_policy_payload(session, {}, exec_ctx)
    for item in merged.get("mandatory_resolution_errors") or []:
        assert not str(item).endswith(str(draft.id))
    session.commit()
    _, ok = _evaluate_apply_paper(session, ctx, apply_count=4, id_prefix="r33-forged-copy")
    assert ok.verdict == PaperDistributionVerdict.PASS


def test_signed_revoke_and_retire_allows_paper_without_mandatory(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_apply40(session, tmp_path, ctx)
    rule = _board_rule(session)
    revision_id = ctx["source_revision_id"]
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
    revoke_token = issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id),
            revision_id=revision_id,
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
        revision_id=revision_id,
        claim_id=claim_id,
        actor_id=MANDATORY_BOARD_POLICY_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=revoke_token,
    )
    session.commit()
    merged = merge_scoped_mandatory_policy_payload(session, {}, _exec_ctx(ctx))
    assert not merged.get("mandatory_resolution_errors")
    _, result = _evaluate_apply_paper(session, ctx, apply_count=5, id_prefix="r33-retired")
    assert result.verdict == PaperDistributionVerdict.PASS
