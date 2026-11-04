"""Day10 R25 — board grant scope, execution-context policy reads, lineage/revoke lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    bootstrap_secret_for_tests,
    issue_mandatory_policy_approve_decision,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_mapping_curator_admin_actor,
    mandatory_board_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, INST_B, _seed_production_institution_graph, _session
from test_day10_r18_trust import (
    MANDATORY_BOARD_POLICY_ACTOR,
    _approve_mandatory_policy_for_rule,
)

from app.curator_auth.bootstrap import provision_operator_credential
from app.curator_auth.issuer import (
    CuratorAuthError,
    CuratorScope,
    issue_curator_write_decision,
    verify_durable_curator_approval,
)
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    _policy_value_checksum,
    _rule_lifecycle_digest,
    mandatory_policy_claim_active,
    mandatory_policy_claim_id,
    mandatory_policy_revoke_binding_payload,
    revoke_mandatory_policy_claim,
)
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload


def _exec_ctx(ctx: dict[str, str], *, board: str = "cbse") -> PaperExecutionContext:
    return PaperExecutionContext(
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        board_code=board,
    )


def test_institution_only_credential_cannot_mint_board_mandatory_claim(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    provision_operator_credential(
        session,
        bootstrap_secret=bootstrap_secret_for_tests(),
        admin_actor=admin,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
        ),
        board_scope_authorized=False,
    )
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=1),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 1}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(rule)
    session.flush()
    lifecycle = _rule_lifecycle_digest(rule)
    value_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    with pytest.raises(CuratorAuthError, match="scope mismatch"):
        issue_mandatory_policy_approve_decision(
            session,
            admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
            operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            rule=rule,
            revision_id=ctx["source_revision_id"],
            value_checksum=value_checksum,
            rule_lifecycle_digest=lifecycle,
        )


def test_board_scope_authorized_false_with_matching_board_code_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    provision_operator_credential(
        session,
        bootstrap_secret=bootstrap_secret_for_tests(),
        admin_actor=admin,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
        board_scope_authorized=False,
    )
    with pytest.raises(CuratorAuthError, match="board mismatch|scope mismatch|credential scope"):
        issue_curator_write_decision(
            session,
            admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
            operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
            role=CuratorRole.MANDATORY_POLICY_CURATOR,
            operation=CuratorOperation.MANDATORY_POLICY_APPROVE,
            binding_payload={
                "policy_rule_id": "x",
                "source_revision_id": ctx["source_revision_id"],
            },
            scope=CuratorScope(
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                board_code="cbse",
            ),
        )


def test_board_wide_claim_active_only_for_matching_execution_board(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=100.0),
    )
    for inst_id in (INST_A, INST_B):
        inst = session.get(Institution, inst_id)
        assert inst is not None
        inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"remember": 100.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
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
        execution_context=_exec_ctx(ctx, board="cbse"),
    )
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
        execution_context=_exec_ctx(ctx, board="icse"),
    )


def test_signed_revoke_verifies_and_blocks_original_read(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=40.0),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"remember": 100.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
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
    value_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=str(rule.id),
        source_revision_id=revision.id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
    )
    exec_ctx = _exec_ctx(ctx)
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
    policy_actor = MANDATORY_BOARD_POLICY_ACTOR
    revoke_token = issue_curator_write_decision(
        session,
        admin_external_code=policy_actor,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule.id), revision_id=revision.id, claim_id=claim_id
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )
    revoke_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=revision.id,
        claim_id=claim_id,
        actor_id=policy_actor,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curator_decision_token=revoke_token,
    )
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


def test_merge_scoped_mandatory_payload_respects_execution_board(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=2),
    )
    for inst_id in (INST_A, INST_B):
        inst = session.get(Institution, inst_id)
        assert inst is not None
        inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
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
    merged = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert merged.get("mandatory_cognitive_ranges")
    foreign = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_B, board_code="icse"),
    )
    assert not foreign.get("mandatory_cognitive_ranges")
