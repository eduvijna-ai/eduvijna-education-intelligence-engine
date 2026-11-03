from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from day10_orchestration_production import (
    build_day10_production_orchestration_request,
    build_day10_production_orchestration_service,
)
from day10_source_lifecycle import (
    ensure_genuine_json_upload_source_approval,
    ensure_genuine_source_content_approval,
    ensure_mapping_curator_admin_actor,
    ensure_mapping_curator_registry,
    mandatory_board_policy_rule,
)
from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import (
    _MAPPING_SOURCE_LOCATOR,
    _approve_revision_mapping_binding,
)
from test_day10_r18_trust import _approve_mandatory_policy_for_rule

from app.core.config import get_settings
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.education_intelligence.context import ValidationContext
from app.models.education_intelligence import ValidationAuditRun
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.orchestration.canonical_mapping import draft_to_canonical
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft, ResolvedScope
from app.orchestration.day6_reuse import (
    current_day6_provenance,
    day6_summary_from_audit_run,
    find_accepted_day6_audit_run,
)
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    approve_mandatory_policy_claim,
    mandatory_policy_claim_active,
)
from app.paper_distribution.mandatory_policy_resolver import PAPER_MANDATORY_POLICY_KEY
from app.prerequisite_intelligence.authority import load_revision_record
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.root_cause_intelligence.enums import RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import apply_mapping_authority_overlay
from app.root_cause_intelligence.mapping_claim_authority import mapping_claim_authorized_for_overlay
from app.root_cause_intelligence.mapping_evidence import verify_revision_content_integrity
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.source_intelligence.storage import LocalSourceStorage


def test_compiled_orchestration_production_root_cause_hitl_replay(tmp_path: Path) -> None:
    domain = _session(tmp_path)
    gateway = FakeGenerationGateway()
    ctx, service, _gw, ki_adapter = build_day10_production_orchestration_service(
        domain,
        tmp_path,
        gateway=gateway,
        memory_checkpointer=False,
    )
    request = build_day10_production_orchestration_request(
        ctx,
        idempotency_key="d10-r21-prod-orch",
        requested_count=2,
        diagnostic_by_slot={
            "0": "diagnostic_clean_pass",
            "1": "diagnostic_correct_mislabeled",
        },
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED, paused.errors
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED, completed.errors
    root_cause = list(completed.metadata_json.get("root_cause_results") or [])
    assert root_cause
    pass_rows = [
        row
        for row in root_cause
        if str(row.get("verdict_status")) == RootCauseVerdictStatus.PASS.value
        and len(row.get("hypotheses") or []) > 0
    ]
    veto_rows = [
        row
        for row in root_cause
        if str(row.get("verdict_status")) != RootCauseVerdictStatus.PASS.value
    ]
    checkpoint = service.compiled_graph.get_state(
        {"configurable": {"thread_id": completed.run_id}}
    )
    checkpoint_values = checkpoint.values or {}
    diagnostic_validation = list(checkpoint_values.get("diagnostic_validation") or [])
    sibling_diagnostic_veto = any(
        item.get("blocking")
        and "correct_option_mislabeled" in list(item.get("issue_codes") or [])
        for item in diagnostic_validation
    )
    assert pass_rows, root_cause
    assert veto_rows or sibling_diagnostic_veto, root_cause
    det = checkpoint_values.get("deterministic_validation") or []
    assert len(det) >= 2
    for row in det:
        assert row.get("day6_validation_run_id")
        assert row.get("input_hash")
        assert row.get("learning_outcome_ids") is not None
        assert row.get("competency_codes") is not None
    control = service._control
    pass_audits = control.scalars(
        select(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "root_cause_item",
            OrchestrationAuditEvent.status == RootCauseVerdictStatus.PASS.value,
        )
    ).all()
    assert pass_audits
    root_cause_audit_count = control.scalar(
        select(func.count())
        .select_from(OrchestrationAuditEvent)
        .where(OrchestrationAuditEvent.node_name == "root_cause_item")
    )
    gateway_calls_after_complete = len(gateway.call_history())
    audit_count = control.scalar(select(func.count()).select_from(OrchestrationAuditEvent))
    service.close()
    service2 = build_orchestration_service(
        domain,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=False,
        force_fake=True,
    )
    replay = service2.run(request, resume=HumanResumeDecision(action="approve"))
    assert replay.run_id == completed.run_id
    assert len(gateway.call_history()) == gateway_calls_after_complete
    assert control.scalar(select(func.count()).select_from(OrchestrationAuditEvent)) == audit_count
    assert (
        control.scalar(
            select(func.count())
            .select_from(OrchestrationAuditEvent)
            .where(OrchestrationAuditEvent.node_name == "root_cause_item")
        )
        == root_cause_audit_count
    )
    service2.close()


def test_mandatory_claim_inactive_after_rule_priority_change(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=_MAPPING_SOURCE_LOCATOR,
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
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=dict(rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=PaperExecutionContext(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )
    rule.priority = 99
    session.flush()
    assert not mandatory_policy_claim_active(
        session,
        rule_id=str(rule.id),
        revision_id=revision.id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=dict(rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=PaperExecutionContext(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )


def test_mandatory_claim_rejects_ungrounded_locator(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator="forged/locator/not-in-source",
    )
    session.add(rule)
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision.policy_rules.append(rule)
    session.flush()
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="grounded|locator"):
        approve_mandatory_policy_claim(
            session,
            rule_id=str(rule.id),
            revision_id=revision.id,
            scope_type=str(rule.scope_type),
            scope_code=str(rule.scope_code),
            policy_key=str(rule.policy_key),
            value_json=dict(rule.value_json or {}),
            actor_id="founder-day10-trust",
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curator_decision_token="invalid",
        )


def test_day6_reuse_requires_current_policy_version(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    scope = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        medium_code="english",
        subject_code="mathematics",
    )
    validation_ctx = ValidationContext.create(
        session, curriculum_version_id=ctx["curriculum_version_id"]
    )
    provenance = current_day6_provenance(validation_ctx)
    item_id = "item-policy-stale"
    digest = "f" * 64
    stale_run = ValidationAuditRun(
        run_id=f"day6-{item_id}-stale",
        input_hash=digest,
        taxonomy_version=validation_ctx.taxonomy.version,
        policy_version="stale-policy@v0",
        aggregate_status="pass",
        blocking_failure=False,
        institution_id=ctx["institution_id"],
        metadata_json={
            "scope": {
                "organization_id": ctx["organization_id"],
                "institution_id": ctx["institution_id"],
                "curriculum_version_id": ctx["curriculum_version_id"],
            },
            "validated_items": [
                {
                    "item_id": item_id,
                    "input_hash": digest,
                    "grade_year_code": "grade-4",
                    "medium_code": "english",
                    "subject_code": "mathematics",
                }
            ],
        },
    )
    session.add(stale_run)
    session.commit()
    assert (
        find_accepted_day6_audit_run(
            session,
            item_id=item_id,
            input_hash=digest,
            scope=scope,
            taxonomy_version=validation_ctx.taxonomy.version,
            policy_version=validation_ctx.policy.version,
            quality_rule_pack_version=str(provenance.get("quality_rule_pack_version") or ""),
            safety_rules_version=str(provenance.get("safety_rules_version") or ""),
            validator_versions=dict(provenance.get("validator_versions") or {}),
        )
        is None
    )


def test_day6_reuse_rejects_stale_quality_rule_pack(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    scope = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        medium_code="english",
        subject_code="mathematics",
    )
    validation_ctx = ValidationContext.create(
        session, curriculum_version_id=ctx["curriculum_version_id"]
    )
    provenance = current_day6_provenance(validation_ctx)
    item_id = "item-quality-stale"
    digest = "c" * 64
    stale_run = ValidationAuditRun(
        run_id=f"day6-{item_id}-quality",
        input_hash=digest,
        taxonomy_version=validation_ctx.taxonomy.version,
        policy_version=validation_ctx.policy.version,
        aggregate_status="pass",
        blocking_failure=False,
        institution_id=ctx["institution_id"],
        metadata_json={
            "quality_rule_pack_version": "stale-quality@v0",
            "safety_rules_version": provenance.get("safety_rules_version"),
            "validator_versions": provenance.get("validator_versions"),
            "scope": {
                "organization_id": ctx["organization_id"],
                "institution_id": ctx["institution_id"],
                "curriculum_version_id": ctx["curriculum_version_id"],
            },
            "validated_items": [
                {
                    "item_id": item_id,
                    "input_hash": digest,
                    "grade_year_code": "grade-4",
                    "medium_code": "english",
                    "subject_code": "mathematics",
                }
            ],
        },
    )
    session.add(stale_run)
    session.commit()
    assert (
        find_accepted_day6_audit_run(
            session,
            item_id=item_id,
            input_hash=digest,
            scope=scope,
            taxonomy_version=validation_ctx.taxonomy.version,
            policy_version=validation_ctx.policy.version,
            quality_rule_pack_version=str(provenance.get("quality_rule_pack_version") or ""),
            safety_rules_version=str(provenance.get("safety_rules_version") or ""),
            validator_versions=dict(provenance.get("validator_versions") or {}),
        )
        is None
    )


def test_mandatory_claim_active_for_default_priority_zero(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=_MAPPING_SOURCE_LOCATOR,
        priority=0,
    )
    assert int(rule.priority) == 0
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
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=dict(rule.value_json or {}),
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        execution_context=PaperExecutionContext(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            board_code="cbse",
        ),
    )


def test_day6_summary_selects_matching_item_not_first_entry(tmp_path: Path) -> None:
    session = _session(tmp_path)
    run = ValidationAuditRun(
        run_id="day6-multi",
        input_hash="a" * 64,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        policy_version="cbse-primary@v1",
        aggregate_status="pass",
        blocking_failure=False,
        metadata_json={
            "validated_items": [
                {"item_id": "first", "input_hash": "a" * 64, "learning_outcome_ids": ["lo-1"]},
                {
                    "item_id": "second",
                    "input_hash": "a" * 64,
                    "learning_outcome_ids": ["lo-2"],
                    "competency_codes": ["application"],
                },
            ]
        },
    )
    session.add(run)
    session.flush()
    _, _, los, codes = day6_summary_from_audit_run(run, item_id="second")
    assert los == ["lo-2"]
    assert codes == ["application"]


def test_canonical_hash_includes_source_revision_ids(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    scope = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    draft = DraftQuestionItem(
        item_id="item-hash",
        slot_index=0,
        stem_text="2 + 2 = ?",
        options=[
            QuestionOptionDraft(option_key="A", text="3", is_correct=False),
            QuestionOptionDraft(option_key="B", text="4", is_correct=True),
        ],
        source_revision_ids=[ctx["source_revision_id"]],
    )
    base = draft_to_canonical(draft, scope, request_marks=1.0).canonical_hash()
    other = draft_to_canonical(
        draft.model_copy(update={"source_revision_ids": [str(uuid4())]}),
        scope,
        request_marks=1.0,
    ).canonical_hash()
    assert base != other


def test_mapping_overlay_read_with_configured_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store_root = tmp_path / "configured-source-store"
    store_root.mkdir()
    monkeypatch.setenv("SOURCE_STORAGE_DIR", str(store_root))
    get_settings.cache_clear()
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    ensure_mapping_curator_registry(session)
    ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    upload_revision, _storage_path = ensure_genuine_json_upload_source_approval(
        session,
        tmp_path,
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
        storage_root=store_root,
    )
    overlay = _approve_revision_mapping_binding(
        session,
        store_root,
        upload_revision.id,
        ctx,
        skip_source_reapproval=True,
    )
    record = load_revision_record(session, upload_revision.id)
    assert record is not None
    assert upload_revision.storage_path
    assert verify_revision_content_integrity(session, record)
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    graph_scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    overlay_entry = apply_mapping_authority_overlay(
        session, load_root_cause_mapping(), graph_scope=graph_scope
    ).resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert overlay_entry is not None
    assert mapping_claim_authorized_for_overlay(
        session,
        record,
        overlay_entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope,
    )
    stored = LocalSourceStorage(str(store_root))
    blob_path = stored._resolve_relative(upload_revision.storage_path)
    blob_path.write_bytes(blob_path.read_bytes() + b"corrupt")
    assert not verify_revision_content_integrity(session, record)
    assert not mapping_claim_authorized_for_overlay(
        session,
        record,
        overlay_entry,
        overlay,
        registry_version="root-cause-mapping@v1",
        graph_scope=graph_scope,
    )
