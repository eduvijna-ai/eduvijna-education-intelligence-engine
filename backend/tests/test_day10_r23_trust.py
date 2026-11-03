"""Day10 R23 — internal authenticated curator mapping and mandatory-policy approvals."""

from __future__ import annotations

from pathlib import Path

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mandatory_policy_with_curator,
    approve_mapping_with_curator,
    ensure_mandatory_policy_curator_credential,
    ensure_mapping_curator_credential,
    issue_mapping_approve_decision,
)
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    mandatory_board_policy_rule,
)
from test_day10_r8_trust import INST_A, _seed_production_institution_graph, _session
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR

from app.curator_auth.issuer import CuratorAuthError, CuratorScope, verify_curator_operator
from app.curator_auth.roles import CuratorRole
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import mandatory_policy_claim_active
from app.prerequisite_intelligence.authority import load_revision_record
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    mapping_claim_authorized_for_overlay,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_actor_id_alone_cannot_mint_mapping_approval_without_credential(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
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
    with pytest.raises(CuratorAuthError, match="credential"):
        issue_mapping_approve_decision(
            session,
            admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
            operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
            approval_context=approval_ctx,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
        )


def test_signed_mapping_and_policy_claims_authorize_production_read(tmp_path: Path) -> None:
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
    ensure_mandatory_policy_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        board_code="cbse",
        board_scope_authorized=True,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    record = load_revision_record(session, revision.id)
    assert record is not None
    overlay = {
        "misconception_code": entry.misconception_code,
        "candidate_concept_codes": list(entry.candidate_concept_codes),
        "source_locator": _MAPPING_SOURCE_LOCATOR,
        "mapping_registry_version": "root-cause-mapping@v1",
        "source_revision_ids": [revision.id],
        "organization_id": ctx["organization_id"],
        "institution_id": ctx["institution_id"],
        "curriculum_version_id": ctx["curriculum_version_id"],
    }
    from app.root_cause_intelligence.mapping_authority import mapping_evidence_checksum
    from app.root_cause_intelligence.mapping_evidence import (
        resolve_approved_source_span,
        source_content_checksum,
    )

    content_checksum = source_content_checksum(record)
    _, span_checksum = resolve_approved_source_span(session, record, _MAPPING_SOURCE_LOCATOR)
    overlay["mapping_evidence_checksum"] = mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        source_revision_id=revision.id,
        source_content_checksum=content_checksum or "",
        source_span_checksum=span_checksum,
    )
    overlay["source_span_checksum"] = span_checksum
    from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope

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
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    session.flush()
    approve_mandatory_policy_with_curator(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
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
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )


def test_wrong_operator_secret_rejected(tmp_path: Path) -> None:
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
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    scope = CuratorScope(
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    with pytest.raises(CuratorAuthError, match="verification failed"):
        verify_curator_operator(
            session,
            admin_external_code=DEFAULT_MAPPING_CURATOR_ACTOR,
            operator_secret="wrong-secret-value-123456",
            role=CuratorRole.MAPPING_CURATOR,
            scope=scope,
        )
