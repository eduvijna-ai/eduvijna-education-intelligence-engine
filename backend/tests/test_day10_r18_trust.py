from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mandatory_policy_with_curator,
    ensure_mandatory_policy_curator_credential,
    ensure_mapping_curator_credential,
    issue_mapping_approve_decision,
)
from day10_day6_binding import seed_production_day6_audit
from day10_source_lifecycle import (
    DEFAULT_MAPPING_CURATOR_ACTOR,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    mandatory_board_policy_rule,
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
)

from app.common.trust_execution import TrustExecutionMode
from app.models.education_intelligence import ValidationAuditRun
from app.models.policy import PolicyRule
from app.models.source import SourceRevision
from app.models.tenancy import AdminActor, Institution
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import (
    DistributionDimensionStatus,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_resolver import (
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)
from app.root_cause_intelligence.day6_binding_verify import verify_production_day6_binding
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def _bootstrap_mapping_curator(session: Session, ctx: dict[str, str]) -> tuple[str, AdminActor]:
    ensure_mapping_curator_registry(session)
    actor_id = f"{DEFAULT_MAPPING_CURATOR_ACTOR}@{ctx['institution_id'][:8]}"
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_id,
    )
    ensure_mapping_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    return actor_id, admin


def _mapping_decision_token(
    session: Session, ctx: dict[str, str], actor_id: str, entry, *, source_locator: str
) -> str:
    approval_ctx = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    return issue_mapping_approve_decision(
        session,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        approval_context=approval_ctx,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=source_locator,
        mapping_registry_version="root-cause-mapping@v1",
    )


def test_mutated_extracted_text_rejects_mapping_claim(tmp_path: Path) -> None:
    from app.root_cause_intelligence.mapping_claim_authority import (
        approve_root_cause_mapping_claim,
    )

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.extracted_text = (
        f"{revision.extracted_text or ''}\n"
        "forged/locator\nFake mapping educational claim appended after approval."
    )
    session.flush()
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    token = _mapping_decision_token(
        session, ctx, actor_id, entry, source_locator="forged/locator"
    )
    with pytest.raises(MappingClaimAuthorityError, match="integrity|fingerprint"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator="forged/locator",
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=actor_id,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            curator_decision_token=token,
        )


def test_curator_impersonation_without_authenticated_writer_rejected(tmp_path: Path) -> None:
    from app.root_cause_intelligence.mapping_claim_authority import (
        approve_root_cause_mapping_claim,
    )

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    with pytest.raises(MappingClaimAuthorityError, match="malformed|invalid|curator"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=MappingClaimApprovalContext(
                actor_id=actor_id,
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            curator_decision_token="forged.token.here",
        )


def test_day6_extra_learning_outcome_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    run_id, binding = seed_production_day6_audit(
        session,
        item_id="item-extra-lo",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    session.commit()
    ok, path = verify_production_day6_binding(
        session,
        item_id="item-extra-lo",
        validation_run_id=run_id,
        input_hash=str(binding["input_hash"]),
        learning_outcome_ids=[str(binding["learning_outcome_ids"][0]), "forged-lo"],
        competency_codes=list(binding["competency_codes"]),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    assert not ok
    assert path == "learning_outcome_ids"


def test_day6_missing_run_scope_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    run = ValidationAuditRun(
        run_id=f"day6-noscope-{uuid4().hex[:8]}",
        input_hash="a" * 64,
        taxonomy_version="cbse-primary@v1",
        policy_version="cbse-primary@v1",
        aggregate_status="pass",
        blocking_failure=False,
        metadata_json={
            "validated_items": [
                {
                    "item_id": "item-noscope",
                    "input_hash": "a" * 64,
                    "learning_outcome_ids": ["lo-1"],
                    "competency_codes": ["knowledge"],
                }
            ],
        },
    )
    session.add(run)
    session.flush()
    ok, path = verify_production_day6_binding(
        session,
        item_id="item-noscope",
        validation_run_id=str(run.id),
        input_hash="a" * 64,
        learning_outcome_ids=["lo-1"],
        competency_codes=["knowledge"],
        institution_id=INST_A,
    )
    assert not ok
    assert path == "institution_id"


def test_root_cause_production_without_control_session_fail_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    snapshot = _load_snapshot(session, ctx)
    request = _root_cause_request(ctx, snapshot, institution_id=ctx["institution_id"])
    result = RootCauseIntelligenceService().analyze(
        request,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=None,
    )
    assert result.verdict_status == RootCauseVerdictStatus.REVIEW_REQUIRED
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert "control_session" in result.field_paths


def _approve_mandatory_policy_for_rule(
    session: Session,
    *,
    rule: PolicyRule,
    revision_id: str,
    actor_id: str = "founder-day10-trust",
    organization_id: str | None = None,
    institution_id: str | None = None,
) -> None:
    from sqlalchemy import select

    revision = session.get(SourceRevision, revision_id)
    assert revision is not None and revision.source is not None
    org = organization_id or str(revision.source.organization_id or "")
    inst = institution_id or str(revision.source.institution_id or "")
    if not org or not inst:
        raise AssertionError(
            "mandatory policy approval requires organization and institution scope"
        )
    admin = session.scalar(select(AdminActor).where(AdminActor.external_code == actor_id))
    if admin is None:
        admin = ensure_mapping_curator_admin_actor(
            session,
            organization_id=org,
            institution_id=inst,
            external_code=actor_id,
            display_name="Day10 policy curator",
        )
    board_code = str(rule.scope_code) if str(rule.scope_type) == "board" else None
    board_scope_authorized = str(rule.scope_type) == "board"
    teacher_id = None
    if str(rule.scope_type) == "teacher":
        from day10_source_lifecycle import ensure_teacher_for_scope

        teacher = ensure_teacher_for_scope(
            session,
            institution_id=inst,
            external_code=str(rule.scope_code),
        )
        teacher_id = str(teacher.id)
    ensure_mandatory_policy_curator_credential(
        session,
        admin,
        organization_id=org,
        institution_id=inst,
        board_code=board_code,
        teacher_id=teacher_id,
        board_scope_authorized=board_scope_authorized,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    approve_mandatory_policy_with_curator(
        session,
        rule=rule,
        revision_id=revision_id,
        organization_id=org,
        institution_id=inst,
        actor_id=actor_id,
        policy_curator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )


def _seed_board_mandatory_remember_two(
    session: Session, tmp_path: Path, ctx: dict[str, str], revision_id: str
) -> None:
    ensure_genuine_source_content_approval(
        session, tmp_path, revision_id, source_locator=_MAPPING_SOURCE_LOCATOR
    )
    for inst_id in (INST_A, INST_B):
        inst = session.get(Institution, inst_id)
        assert inst is not None
        inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    revision = session.get(SourceRevision, revision_id)
    assert revision is not None
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=revision_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)


def _paper_item_from_validated(validated: dict) -> PaperItemInput:
    return PaperItemInput(
        item_id=str(validated["item_id"]),
        marks=1.0,
        cognitive_level=str(validated.get("declared_cognitive_level")),
        competency_codes=list(validated.get("competency_codes") or []),
        day6_validated=True,
        metadata_json={
            "day6_input_hash": validated.get("input_hash"),
            "curriculum_version_id": validated.get("curriculum_version_id"),
            "grade_year_code": validated.get("grade_year_code"),
            "medium_code": validated.get("medium_code"),
            "subject_code": validated.get("subject_code"),
            "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
        },
    )


def _remember_paper_with_day6_bindings(
    session: Session, ctx: dict[str, str], item_count: int, *, id_prefix: str
) -> tuple[PaperDistributionRequest, PaperDay6TrustContext]:
    items: list[PaperItemInput] = []
    bindings: list[PaperDay6ItemBinding] = []
    for index in range(item_count):
        item_id = f"{id_prefix}-remember-{index}"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=ctx["organization_id"],
            institution_id=INST_A,
            curriculum_version_id=ctx["curriculum_version_id"],
            declared_cognitive_level="remember",
        )
        bindings.append(PaperDay6ItemBinding(item_id=item_id, validation_run_id=run_id))
        items.append(_paper_item_from_validated(validated))
    request = PaperDistributionRequest(
        paper_id=f"board-mandatory-{item_count}-remember",
        items=items,
        cognitive_targets=[],
        competency_targets=[],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    return request, PaperDay6TrustContext.from_item_bindings(bindings)


def test_board_mandatory_exact_count_enforces_without_voluntary_targets(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    _seed_board_mandatory_remember_two(session, tmp_path, ctx, ctx["source_revision_id"])
    payload = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    ranges = payload.get("mandatory_cognitive_ranges") or []
    assert any(
        str(entry.get("key")) == "remember" and int(entry.get("exact_count") or 0) == 2
        for entry in ranges
        if isinstance(entry, dict)
    )
    session.commit()
    three_item, three_trust = _remember_paper_with_day6_bindings(
        session, ctx, 3, id_prefix="three"
    )
    fail_result = evaluate_paper_distribution_with_session(
        session,
        three_item,
        day6_trust=three_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert fail_result.cognitive_summary.status == DistributionDimensionStatus.FAIL
    two_item, two_trust = _remember_paper_with_day6_bindings(
        session, ctx, 2, id_prefix="two"
    )
    pass_result = evaluate_paper_distribution_with_session(
        session,
        two_item,
        day6_trust=two_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert pass_result.verdict == PaperDistributionVerdict.PASS


def test_board_mandatory_exact_percent_from_rule_map(tmp_path: Path) -> None:
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
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=ctx["source_revision_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)
    session.commit()
    payload = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    merged = payload.get("mandatory_cognitive_ranges") or []
    assert any(
        isinstance(entry, dict)
        and entry.get("key") == "apply"
        and entry.get("exact_percent") == 40.0
        for entry in merged
    )
    apply_paper, apply_trust = _apply_paper_with_day6_bindings(session, ctx, apply_count=4)
    pass_result = evaluate_paper_distribution_with_session(
        session,
        apply_paper,
        day6_trust=apply_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert pass_result.verdict == PaperDistributionVerdict.PASS
    fail_paper, fail_trust = _apply_paper_with_day6_bindings(session, ctx, apply_count=5)
    fail_result = evaluate_paper_distribution_with_session(
        session,
        fail_paper,
        day6_trust=fail_trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert fail_result.verdict != PaperDistributionVerdict.PASS


def _apply_paper_with_day6_bindings(
    session: Session,
    ctx: dict[str, str],
    *,
    apply_count: int,
    total: int = 10,
) -> tuple[PaperDistributionRequest, PaperDay6TrustContext]:
    items: list[PaperItemInput] = []
    bindings: list[PaperDay6ItemBinding] = []
    cognitive_levels = ["apply"] * apply_count + ["remember"] * (total - apply_count)
    for index, level in enumerate(cognitive_levels):
        item_id = f"board-apply40-{apply_count}-{index}"
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
        paper_id=f"board-apply40-{apply_count}",
        items=items,
        cognitive_targets=[],
        competency_targets=[],
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
    )
    return request, PaperDay6TrustContext.from_item_bindings(bindings)
