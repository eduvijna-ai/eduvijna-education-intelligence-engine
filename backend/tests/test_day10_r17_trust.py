from __future__ import annotations

from pathlib import Path

import pytest
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    mandatory_board_policy_rule,
    mandatory_institution_policy_rule,
    mandatory_teacher_policy_rule,
)
from sqlalchemy.orm import Session
from test_day10_r8_trust import (
    INST_A,
    INST_B,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import (
    _MAPPING_SOURCE_LOCATOR,
    _approve_revision_mapping_binding,
)

from app.common.trust_execution import TrustExecutionMode
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.policy import PolicyRule
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    approve_mandatory_policy_claim,
)
from app.paper_distribution.mandatory_policy_resolver import (
    mandatory_policy_context_errors,
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    paper_targets_authorized,
)
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.root_cause_intelligence.day6_binding_verify import verify_production_day6_binding
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    apply_mapping_authority_overlay,
    mapping_entry_production_authorized,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    approve_root_cause_mapping_claim,
    issue_mapping_claim_writer_attestation,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def _approve_mandatory_policy_for_rule(
    session: Session,
    *,
    rule: PolicyRule,
    revision_id: str,
    actor_id: str = "founder-day10-trust",
) -> None:
    approve_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=revision_id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_json=dict(rule.value_json or {}),
        actor_id=actor_id,
    )


def test_mutated_manual_metadata_excerpt_rejects_new_mapping_claim(tmp_path: Path) -> None:
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
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    meta = dict(revision.metadata_json or {})
    manual = dict(meta.get("manual_metadata") or {})
    manual["excerpt"] = "Forged educational mapping claim text."
    meta["manual_metadata"] = manual
    revision.metadata_json = meta
    session.flush()
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError, match="integrity|metadata excerpt"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            attestation=issue_mapping_claim_writer_attestation(
                session,
                MappingClaimApprovalContext(
                    actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
                    organization_id=ctx["organization_id"],
                    institution_id=ctx["institution_id"],
                    curriculum_version_id=ctx["curriculum_version_id"],
                ),
            ),
        )


def test_registry_string_without_admin_actor_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError, match="authorized curator"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            attestation=issue_mapping_claim_writer_attestation(
                session,
                MappingClaimApprovalContext(
                    actor_id=DEFAULT_MAPPING_CURATOR_ACTOR,
                    organization_id=ctx["organization_id"],
                    institution_id=ctx["institution_id"],
                    curriculum_version_id=ctx["curriculum_version_id"],
                ),
            ),
        )


def test_production_day6_binding_fail_closed_without_run_id(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ok, path = verify_production_day6_binding(
        session,
        item_id="item-1",
        validation_run_id=None,
        input_hash="abc",
        learning_outcome_ids=["lo-1"],
        competency_codes=["knowledge"],
    )
    assert not ok
    assert path == "day6_validation_run_id"


def test_root_cause_production_missing_day6_run_review_required(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    snapshot = _load_snapshot(session, ctx)
    request = _root_cause_request(ctx, snapshot, institution_id=ctx["institution_id"])
    request = request.model_copy(
        update={
            "day6_validation_run_id": None,
            "day6_input_hash": None,
            "learning_outcome_ids": [],
            "competency_codes": [],
        }
    )
    result = RootCauseIntelligenceService().analyze(
        request,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.verdict_status == RootCauseVerdictStatus.REVIEW_REQUIRED
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes


def test_board_institution_exact_count_conflict(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst_a = session.get(Institution, INST_A)
    assert inst_a is not None
    inst_a.metadata_json = {**(inst_a.metadata_json or {}), "board_code": "cbse"}
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    inst_rule = mandatory_institution_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 3}]},
        institution_id=INST_A,
        priority=5,
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(board_rule)
    session.add(inst_rule)
    session.flush()
    revision.policy_rules.extend([board_rule, inst_rule])
    _approve_mandatory_policy_for_rule(session, rule=board_rule, revision_id=revision.id)
    _approve_mandatory_policy_for_rule(session, rule=inst_rule, revision_id=revision.id)
    ensure_paper_target_policy_configured(session)
    session.commit()
    payload = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert payload.get("mandatory_resolution_errors")


def test_mismatched_board_code_is_veto_not_bypass(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _seed_production_institution_graph(session)
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    session.commit()
    errors = mandatory_policy_context_errors(
        session,
        PaperExecutionContext(institution_id=INST_A, board_code="icse"),
    )
    assert errors == ["execution_context.board_code"]


def test_independent_scoped_claims_per_institution(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx_a = _seed_production_institution_graph(session)
    ctx_b = {**ctx_a, "institution_id": INST_B}
    overlay_a = _approve_revision_mapping_binding(
        session, tmp_path, ctx_a["source_revision_id"], ctx_a
    )
    overlay_b = _approve_revision_mapping_binding(
        session, tmp_path, ctx_a["source_revision_id"], ctx_b
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [overlay_a, overlay_b]},
        )
    )
    session.commit()
    scope_a = PrerequisiteGraphScope(
        curriculum_version_id=ctx_a["curriculum_version_id"],
        organization_id=ctx_a["organization_id"],
        institution_id=ctx_a["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    scope_b = scope_a.model_copy(update={"institution_id": INST_B})
    entry_a = apply_mapping_authority_overlay(
        session, load_root_cause_mapping(), graph_scope=scope_a
    ).resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    entry_b = apply_mapping_authority_overlay(
        session, load_root_cause_mapping(), graph_scope=scope_b
    ).resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry_a and entry_b
    assert mapping_entry_production_authorized(
        session, entry_a, graph_scope=scope_a, mapping_registry_version="root-cause-mapping@v1"
    )
    assert mapping_entry_production_authorized(
        session, entry_b, graph_scope=scope_b, mapping_registry_version="root-cause-mapping@v1"
    )


def test_paper_targets_reject_board_teacher_exact_percent_conflict(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    board_rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    teacher_rule = mandatory_teacher_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 20.0}},
        teacher_id="teacher-a",
        priority=1,
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(board_rule)
    session.add(teacher_rule)
    session.flush()
    revision.policy_rules.extend([board_rule, teacher_rule])
    _approve_mandatory_policy_for_rule(session, rule=board_rule, revision_id=revision.id)
    _approve_mandatory_policy_for_rule(session, rule=teacher_rule, revision_id=revision.id)
    ensure_paper_target_policy_configured(session)
    session.commit()
    request = PaperDistributionRequest(
        paper_id="paper-r17",
        requested_count=10,
        items=[
            PaperItemInput(item_id=f"i{n}", marks=1.0, cognitive_level="apply") for n in range(10)
        ],
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="apply", exact_percent=40.0)
        ],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    ok, field = paper_targets_authorized(
        session,
        request,
        version=PAPER_TARGET_POLICY_VERSION,
        execution_context=PaperExecutionContext(
            institution_id=INST_A,
            board_code="cbse",
            teacher_id="teacher-a",
        ),
    )
    assert not ok
    assert field is not None
