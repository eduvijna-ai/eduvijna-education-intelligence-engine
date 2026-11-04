"""Day10 R26 — revoke claim binding, board authority, execution context, audit actor."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mapping_with_curator,
    ensure_mapping_curator_credential,
    issue_mapping_revoke_decision,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    mandatory_board_policy_rule,
)
from sqlalchemy import select
from test_day10_r8_trust import INST_A, INST_B, ORG_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR
from test_day10_r18_trust import MANDATORY_BOARD_POLICY_ACTOR, _approve_mandatory_policy_for_rule

from app.curator_auth.issuer import (
    CuratorOperation,
    CuratorScope,
    issue_curator_write_decision,
    operation_binding_digest,
)
from app.curator_auth.roles import CuratorRole
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    mandatory_policy_claim_active,
    mandatory_policy_revoke_binding_payload,
    revoke_mandatory_policy_claim,
)
from app.paper_distribution.mandatory_policy_resolver import merge_scoped_mandatory_policy_payload
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    mapping_revoke_binding_payload,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_revoke_operation_binding_digest_includes_claim_id() -> None:
    revision = "rev-1"
    digest_a = operation_binding_digest(
        CuratorOperation.MAPPING_REVOKE.value,
        mapping_revoke_binding_payload(revision_id=revision, claim_id="claim-a"),
    )
    digest_b = operation_binding_digest(
        CuratorOperation.MAPPING_REVOKE.value,
        mapping_revoke_binding_payload(revision_id=revision, claim_id="claim-b"),
    )
    assert digest_a != digest_b


def test_mapping_revoke_token_for_claim_a_rejects_claim_b(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_mapping_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    claim_a = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    claim_b = "00000000-0000-0000-0000-000000000099"
    token = issue_mapping_revoke_decision(
        session,
        admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_a,
    )
    with pytest.raises(MappingClaimAuthorityError, match="not active|binding|mismatch"):
        revoke_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            claim_id=claim_b,
            actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
            curator_decision_token=token,
            approval_context=approval_ctx,
        )
    still_active = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == ctx["source_revision_id"],
            SourceAuditEvent.event_type == "root_cause_mapping_claim_approved",
        )
    ).all()
    assert any(str((e.payload_json or {}).get("claim_id")) == claim_a for e in still_active)


def test_synthetic_test_policy_flag_does_not_bypass_board_source(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 1}]},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    rule.metadata_json = {
        **(rule.metadata_json or {}),
        "synthetic_test_policy": True,
    }
    session.add(rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(rule)
    session.flush()
    revision.source.board_or_exam = None
    session.flush()
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="board"):
        from app.paper_distribution.mandatory_policy_claim_authority import (
            _verify_scope_source_trust,
        )

        _verify_scope_source_trust(session, rule, revision)


def test_mandatory_claim_active_rejects_board_spoof_and_missing_teacher(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    from day10_source_lifecycle import default_board_mandatory_excerpt

    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=100.0),
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
            institution_id=INST_A,
            board_code="cbse",
        ),
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
        execution_context=PaperExecutionContext(
            institution_id=INST_A,
            board_code="icse",
        ),
    )
    from day10_source_lifecycle import ensure_teacher_for_scope, mandatory_teacher_policy_rule

    from app.paper_distribution.mandatory_policy_claim_authority import (
        _policy_claim_applies_to_execution_context,
    )

    teacher = ensure_teacher_for_scope(session, institution_id=INST_A, external_code="t-r26")
    teacher_rule = mandatory_teacher_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "apply", "exact_count": 1}]},
        teacher_id=str(teacher.id),
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    assert not _policy_claim_applies_to_execution_context(
        session,
        teacher_rule,
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert _policy_claim_applies_to_execution_context(
        session,
        teacher_rule,
        PaperExecutionContext(
            institution_id=INST_A,
            board_code="cbse",
            teacher_id=str(teacher.id),
        ),
    )


def test_tampered_audit_actor_rejected_on_mandatory_read(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    from day10_source_lifecycle import default_board_mandatory_excerpt

    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=100.0),
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
    event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type == "paper_mandatory_policy_claim_approved",
        )
    ).first()
    assert event is not None
    event.actor_id = "forged-actor-id"
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
        execution_context=PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )


def test_board_mandatory_applies_to_two_cbse_institutions_not_icse(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    from day10_source_lifecycle import default_board_mandatory_excerpt

    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(remember_exact_count=2),
    )
    for inst_id, board in ((INST_A, "cbse"), (INST_B, "cbse")):
        inst = session.get(Institution, inst_id)
        assert inst is not None
        inst.metadata_json = {**(inst.metadata_json or {}), "board_code": board}
    icse_inst = Institution(
        organization_id=ORG_A,
        code="r26-icse",
        name="ICSE Inst",
        metadata_json={"board_code": "icse"},
    )
    session.add(icse_inst)
    session.flush()
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        scope_code="cbse",
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
    for inst_id in (INST_A, INST_B):
        merged = merge_scoped_mandatory_policy_payload(
            session,
            {},
            PaperExecutionContext(institution_id=inst_id, board_code="cbse"),
        )
        assert merged.get("mandatory_cognitive_ranges")
    icse_merged = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=icse_inst.id, board_code="icse"),
    )
    assert not icse_merged.get("mandatory_cognitive_ranges")


def test_policy_revoke_token_bound_to_claim_id(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    from day10_source_lifecycle import default_board_mandatory_excerpt

    ensure_board_mandatory_source_evidence(
        session,
        tmp_path,
        ctx["source_revision_id"],
        board_code="cbse",
        policy_excerpt=default_board_mandatory_excerpt(apply_exact_percent=100.0),
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    rule_a = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"remember": 100.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    rule_b = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"understand": 100.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
        priority=11,
    )
    session.add(rule_a)
    session.add(rule_b)
    session.flush()
    revision.policy_rules.extend([rule_a, rule_b])
    _approve_mandatory_policy_for_rule(
        session, rule=rule_a, revision_id=revision.id,
        organization_id=ctx["organization_id"], institution_id=ctx["institution_id"],
    )
    _approve_mandatory_policy_for_rule(
        session, rule=rule_b, revision_id=revision.id,
        organization_id=ctx["organization_id"], institution_id=ctx["institution_id"],
    )
    from app.paper_distribution.mandatory_policy_claim_authority import (
        _policy_value_checksum,
        _rule_lifecycle_digest,
        mandatory_policy_claim_id,
    )

    lifecycle_a = _rule_lifecycle_digest(rule_a)
    claim_a = mandatory_policy_claim_id(
        policy_rule_id=str(rule_a.id),
        source_revision_id=revision.id,
        scope_type=str(rule_a.scope_type),
        scope_code=str(rule_a.scope_code),
        policy_key=str(rule_a.policy_key),
        value_checksum=_policy_value_checksum(dict(rule_a.value_json or {})),
        rule_lifecycle_digest=lifecycle_a,
    )
    lifecycle_b = _rule_lifecycle_digest(rule_b)
    claim_b = mandatory_policy_claim_id(
        policy_rule_id=str(rule_b.id),
        source_revision_id=revision.id,
        scope_type=str(rule_b.scope_type),
        scope_code=str(rule_b.scope_code),
        policy_key=str(rule_b.policy_key),
        value_checksum=_policy_value_checksum(dict(rule_b.value_json or {})),
        rule_lifecycle_digest=lifecycle_b,
    )

    token = issue_curator_write_decision(
        session,
        admin_external_code=MANDATORY_BOARD_POLICY_ACTOR,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
        binding_payload=mandatory_policy_revoke_binding_payload(
            rule_id=str(rule_a.id), revision_id=revision.id, claim_id=claim_a
        ),
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )
    with pytest.raises(MandatoryPolicyClaimAuthorityError):
        revoke_mandatory_policy_claim(
            session,
            rule_id=str(rule_a.id),
            revision_id=revision.id,
            claim_id=claim_b,
            actor_id=MANDATORY_BOARD_POLICY_ACTOR,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curator_decision_token=token,
        )
