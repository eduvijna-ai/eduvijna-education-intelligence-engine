from __future__ import annotations

from pathlib import Path

import pytest
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
)
from test_day10_r8_trust import (
    INST_A,
    INST_B,
    _day9_audit,
    _load_snapshot,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import (
    _MAPPING_SOURCE_LOCATOR,
    _approve_revision_mapping_binding,
)

from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import PolicyScopeType
from app.models.policy import PolicyRule
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_resolver import (
    PAPER_MANDATORY_POLICY_KEY,
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    apply_mapping_authority_overlay,
    mapping_entry_production_authorized,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    MappingClaimWriterAttestation,
    approve_root_cause_mapping_claim,
    issue_mapping_claim_writer_attestation,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_fake_locator_rejected_for_mapping_claim(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    actor_id = f"{DEFAULT_MAPPING_CURATOR_ACTOR}@{ctx['institution_id'][:8]}"
    ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_id,
    )
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError, match="locator"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator="made-up/locator/path",
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=actor_id,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            attestation=issue_mapping_claim_writer_attestation(
                session,
                MappingClaimApprovalContext(
                    actor_id=actor_id,
                    organization_id=ctx["organization_id"],
                    institution_id=ctx["institution_id"],
                    curriculum_version_id=ctx["curriculum_version_id"],
                ),
            ),
        )


def test_unauthorized_curator_actor_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    actor_id = f"{DEFAULT_MAPPING_CURATOR_ACTOR}@{ctx['institution_id'][:8]}"
    ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_id,
    )
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError, match="attestation|authorized curator"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id="random-teacher-actor",
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            attestation=MappingClaimWriterAttestation(
                actor_external_code="random-teacher-actor",
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
                teacher_id=None,
                attestation_ref="forged",
            ),
        )


def test_scoped_mapping_overlays_do_not_cross_institutions(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx_a = _seed_production_institution_graph(session)
    overlay_a = _approve_revision_mapping_binding(
        session, tmp_path, ctx_a["source_revision_id"], ctx_a
    )
    overlay_b = dict(overlay_a)
    overlay_b["institution_id"] = INST_B
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [overlay_a, overlay_b]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000041"
    _day9_audit(session, ctx_a, audit_id=audit_id)
    session.commit()
    _load_snapshot(session, ctx_a)
    scope_a = PrerequisiteGraphScope(
        curriculum_version_id=ctx_a["curriculum_version_id"],
        organization_id=ctx_a["organization_id"],
        institution_id=ctx_a["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    scope_b = scope_a.model_copy(update={"institution_id": INST_B})
    registry_a = apply_mapping_authority_overlay(
        session, load_root_cause_mapping(), graph_scope=scope_a
    )
    entry_a = registry_a.resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry_a is not None
    assert mapping_entry_production_authorized(
        session, entry_a, graph_scope=scope_a, mapping_registry_version="root-cause-mapping@v1"
    )
    registry_b = apply_mapping_authority_overlay(
        session, load_root_cause_mapping(), graph_scope=scope_b
    )
    entry_b = registry_b.resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry_b is not None
    assert not mapping_entry_production_authorized(
        session, entry_b, graph_scope=scope_b, mapping_registry_version="root-cause-mapping@v1"
    )


def test_board_mandatory_policy_applies_to_both_institutions(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    inst_a = session.get(Institution, INST_A)
    inst_b = session.get(Institution, INST_B)
    assert inst_a and inst_b
    inst_a.metadata_json = {**(inst_a.metadata_json or {}), "board_code": "cbse"}
    inst_b.metadata_json = {**(inst_b.metadata_json or {}), "board_code": "cbse"}
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    rule = PolicyRule(
        scope_type=PolicyScopeType.BOARD.value,
        scope_code="cbse",
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json={
            "mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}],
        },
        priority=10,
        active=True,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    session.flush()
    ensure_genuine_source_content_approval(
        session,
        tmp_path,
        ctx["source_revision_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    from app.paper_distribution.mandatory_policy_claim_authority import (
        approve_mandatory_policy_claim,
    )

    approve_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=ctx["source_revision_id"],
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_json=dict(rule.value_json or {}),
        actor_id="founder-day10-trust",
    )
    from app.paper_distribution.mandatory_policy_resolver import (
        _revision_authorized_for_policy,
    )

    assert _revision_authorized_for_policy(session, rule)
    ensure_paper_target_policy_configured(session)
    session.commit()
    from app.paper_distribution.target_policy_registry import (
        load_active_paper_target_policy,
    )

    base_payload = load_active_paper_target_policy(session, PAPER_TARGET_POLICY_VERSION)
    for institution_id in (INST_A, INST_B):
        merged = merge_scoped_mandatory_policy_payload(
            session,
            base_payload,
            PaperExecutionContext(institution_id=institution_id, board_code="cbse"),
        )
        assert merged.get("resolved_board_code") == "cbse"
        assert merged.get("mandatory_cognitive_ranges")
