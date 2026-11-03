"""Day10 R24 — curator auth security boundary (bootstrap, envelope, scope, replay)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    approve_mapping_with_curator,
    bootstrap_secret_for_tests,
    ensure_mapping_curator_credential,
    issue_mapping_approve_decision,
    issue_mapping_revoke_decision,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
)
from sqlalchemy import select
from test_day10_r8_trust import _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR

from app.core.config import get_settings
from app.curator_auth.bootstrap import provision_operator_credential
from app.curator_auth.issuer import (
    CuratorAuthError,
    CuratorScope,
    _decode_token,
    _require_signing_key,
    issue_curator_write_decision,
    verify_durable_curator_approval,
)
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.source import SourceAuditEvent
from app.models.tenancy import Institution
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    mapping_approve_binding_payload,
    mapping_claim_authorized_for_overlay,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_bootstrap_secret_required_for_credential_provision(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    scope = CuratorScope(
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    with pytest.raises(CuratorAuthError, match="bootstrap"):
        provision_operator_credential(
            session,
            bootstrap_secret="wrong-bootstrap-secret-value-0123456789abcdef",
            admin_actor=admin,
            role=CuratorRole.MAPPING_CURATOR,
            operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
            scope=scope,
        )


def test_weak_curator_signing_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURATOR_APPROVAL_SIGNING_KEY", "x")
    get_settings.cache_clear()
    with pytest.raises(CuratorAuthError, match="too short"):
        _require_signing_key()
    get_settings.cache_clear()


def test_decision_token_ttl_clamped_to_max_300_seconds(tmp_path: Path) -> None:
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
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    token = issue_mapping_approve_decision(
        session,
        admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
    )
    _, signing_key = _require_signing_key()
    payload = _decode_token(token, signing_key)
    assert int(payload["exp"]) - int(payload["iat"]) <= 300


def test_tampered_durable_admin_actor_id_fails_read_verification(tmp_path: Path) -> None:
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
    claim_id = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    event = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == ctx["source_revision_id"],
            SourceAuditEvent.event_type == "root_cause_mapping_claim_approved",
        )
    ).first()
    assert event is not None
    tampered = copy.deepcopy(event.payload_json or {})
    tampered["curator_approval"]["admin_actor_id"] = "00000000-0000-0000-0000-000000000000"
    binding = mapping_approve_binding_payload(
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    assert not verify_durable_curator_approval(
        session,
        tampered,
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_APPROVE,
        binding_payload=binding,
        source_audit_event_id=event.id,
    )
    assert claim_id


def test_wrong_board_scope_on_write_decision_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    inst = session.get(Institution, ctx["institution_id"])
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    session.flush()
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    inst = session.get(Institution, ctx["institution_id"])
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    session.flush()
    provision_operator_credential(
        session,
        bootstrap_secret=bootstrap_secret_for_tests(),
        admin_actor=admin,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        scope=CuratorScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
        board_scope_authorized=True,
    )
    with pytest.raises(CuratorAuthError, match="board mismatch|scope mismatch|credential scope"):
        issue_curator_write_decision(
            session,
            admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
            operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
            role=CuratorRole.MANDATORY_POLICY_CURATOR,
            operation=CuratorOperation.MANDATORY_POLICY_APPROVE,
            binding_payload={
                "policy_rule_id": "x",
                "source_revision_id": ctx["source_revision_id"],
            },
            scope=CuratorScope(
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                board_code="icse",
            ),
        )


def test_unsigned_revoke_ignored_signed_revoke_blocks_read(tmp_path: Path) -> None:
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
    claim_id = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    from app.prerequisite_intelligence.authority import load_revision_record
    from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
    from app.root_cause_intelligence.mapping_evidence import (
        mapping_evidence_checksum,
        resolve_approved_source_span,
        source_content_checksum,
    )

    record = load_revision_record(session, ctx["source_revision_id"])
    assert record is not None
    overlay = {
        "misconception_code": entry.misconception_code,
        "candidate_concept_codes": list(entry.candidate_concept_codes),
        "source_locator": _MAPPING_SOURCE_LOCATOR,
        "mapping_registry_version": "root-cause-mapping@v1",
        "source_revision_ids": [record.revision_id],
        "organization_id": ctx["organization_id"],
        "institution_id": ctx["institution_id"],
        "curriculum_version_id": ctx["curriculum_version_id"],
    }
    content_checksum = source_content_checksum(record)
    _, span_checksum = resolve_approved_source_span(session, record, _MAPPING_SOURCE_LOCATOR)
    overlay["mapping_evidence_checksum"] = mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        source_revision_id=record.revision_id,
        source_content_checksum=content_checksum or "",
        source_span_checksum=span_checksum,
    )
    overlay["source_span_checksum"] = span_checksum
    graph_scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    assert mapping_claim_authorized_for_overlay(
        session,
        record,
        entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope,
    )
    session.add(
        SourceAuditEvent(
            source_id=record.source_id,
            source_revision_id=record.revision_id,
            event_type="root_cause_mapping_claim_revoked",
            actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
            outcome="success",
            payload_json={"claim_id": claim_id, "claim_status": "revoked"},
        )
    )
    session.flush()
    assert mapping_claim_authorized_for_overlay(
        session,
        record,
        entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope,
    )
    token = issue_mapping_revoke_decision(
        session,
        admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
    )
    revoke_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
        curator_decision_token=token,
        approval_context=approval_ctx,
    )
    assert not mapping_claim_authorized_for_overlay(
        session,
        record,
        entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope,
    )


def test_replayed_write_decision_token_rejected_on_second_consume(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
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
    from app.root_cause_intelligence.mapping_claim_authority import (
        MappingClaimAuthorityError,
        approve_root_cause_mapping_claim,
    )

    token = issue_mapping_approve_decision(
        session,
        admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
    )
    approve_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
        curator_decision_token=token,
    )
    with pytest.raises(MappingClaimAuthorityError, match="consumed|unknown|jti"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=approval_ctx,
            curator_decision_token=token,
        )
