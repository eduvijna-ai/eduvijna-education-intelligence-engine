from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from day10_curator_auth import (
    DEFAULT_MAPPING_CURATOR_SECRET,
    approve_mapping_with_curator,
    issue_mapping_revoke_decision,
)
from day10_source_lifecycle import (
    ensure_genuine_json_upload_source_approval,
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
)
from test_day10_r18_trust import _bootstrap_mapping_curator, _mapping_decision_token

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.curator_auth.issuer import CuratorAuthError
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceAuditEvent, SourceRevision
from app.models.tenancy import Institution, Teacher
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.factory import build_orchestration_service
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.nodes.validate import deterministic_validate_node
from app.orchestration.state import OrchestrationGraphState
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_resolver import (
    merge_scoped_mandatory_policy_payload,
)
from app.paper_distribution.target_policy_registry import ensure_paper_target_policy_configured
from app.prerequisite_intelligence.authority import load_revision_record
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    MappingClaimAuthorityError,
    approve_root_cause_mapping_claim,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.mapping_evidence import (
    resolve_approved_source_span,
    verify_revision_content_integrity,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping


def test_json_upload_source_integrity_allows_mapping_claim(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    revision, storage_root = ensure_genuine_json_upload_source_approval(
        session,
        tmp_path,
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    record = load_revision_record(session, revision.id)
    assert record is not None
    assert verify_revision_content_integrity(session, record, storage_root=storage_root)
    excerpt, _ = resolve_approved_source_span(
        session, record, _MAPPING_SOURCE_LOCATOR, storage_root=storage_root
    )
    assert _MAPPING_SOURCE_LOCATOR in excerpt or "whole-number" in excerpt
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    approve_mapping_with_curator(
        session,
        revision_id=revision.id,
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=approval_ctx,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
        storage_root=storage_root,
    )


def test_json_upload_tampered_storage_bytes_reject_mapping_claim(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    revision, storage_root = ensure_genuine_json_upload_source_approval(
        session,
        tmp_path,
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    assert revision.storage_path
    stored_file = Path(storage_root) / revision.storage_path
    stored_file.write_bytes(stored_file.read_bytes() + b"tamper")
    record = load_revision_record(session, revision.id)
    assert record is not None
    assert not verify_revision_content_integrity(session, record, storage_root=storage_root)
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    token = _mapping_decision_token(
        session,
        {**ctx, "source_revision_id": revision.id},
        actor_id,
        entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    with pytest.raises(MappingClaimAuthorityError, match="integrity"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=revision.id,
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=approval_ctx,
            curator_decision_token=token,
            storage_root=storage_root,
        )


def test_mandatory_policy_without_claim_not_merged(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    from day10_source_lifecycle import ensure_genuine_source_content_approval

    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.metadata_json = {**(inst.metadata_json or {}), "board_code": "cbse"}
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_ranges": [{"key": "remember", "exact_count": 2}]},
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    ensure_paper_target_policy_configured(session)
    session.commit()
    payload = merge_scoped_mandatory_policy_payload(
        session,
        {},
        PaperExecutionContext(institution_id=INST_A, board_code="cbse"),
    )
    assert not payload.get("mandatory_cognitive_ranges")


def test_inactive_institution_rejects_mandatory_context(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _seed_production_institution_graph(session)
    inst = session.get(Institution, INST_A)
    assert inst is not None
    inst.active = False
    session.commit()
    from app.paper_distribution.mandatory_policy_resolver import mandatory_policy_context_errors

    errors = mandatory_policy_context_errors(
        session, PaperExecutionContext(institution_id=INST_A, board_code="cbse")
    )
    assert errors == ["execution_context.institution_id"]


def test_mapping_claim_teacher_scope_independent_revocation(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    teacher_a = Teacher(
        id=str(uuid4()),
        institution_id=ctx["institution_id"],
        external_code="teacher-a-r19",
        display_name="Teacher A",
        active=True,
    )
    teacher_b = Teacher(
        id=str(uuid4()),
        institution_id=ctx["institution_id"],
        external_code="teacher-b-r19",
        display_name="Teacher B",
        active=True,
    )
    session.add_all([teacher_a, teacher_b])
    session.flush()
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    from day10_source_lifecycle import ensure_genuine_source_content_approval

    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    ctx_a = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        teacher_id=teacher_a.id,
    )
    ctx_b = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        teacher_id=teacher_b.id,
    )
    claim_a = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=ctx_a,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    claim_b = approve_mapping_with_curator(
        session,
        revision_id=ctx["source_revision_id"],
        entry=entry,
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        approval_context=ctx_b,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
    )
    assert claim_a != claim_b
    revoke_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_a,
        actor_id=actor_id,
        approval_context=ctx_a,
        curator_decision_token=issue_mapping_revoke_decision(
            session,
            admin_external_code=actor_id,
            operator_secret=DEFAULT_MAPPING_CURATOR_SECRET,
            approval_context=ctx_a,
            revision_id=ctx["source_revision_id"],
            claim_id=claim_a,
        ),
    )
    session.flush()
    revoked = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == ctx["source_revision_id"],
            SourceAuditEvent.event_type == "root_cause_mapping_claim_revoked",
        )
    ).all()
    assert any(str((event.payload_json or {}).get("claim_id")) == claim_a for event in revoked)
    assert claim_a != claim_b


def test_matched_actor_strings_without_valid_attestation_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    actor_id, _admin = _bootstrap_mapping_curator(session, ctx)
    from day10_source_lifecycle import ensure_genuine_source_content_approval

    ensure_genuine_source_content_approval(
        session, tmp_path, ctx["source_revision_id"], source_locator=_MAPPING_SOURCE_LOCATOR
    )
    entry = load_root_cause_mapping().resolve("MATH.ADD.WHOLE.OFF_BY_ONE_LOW")
    assert entry is not None
    approval_ctx = MappingClaimApprovalContext(
        actor_id=actor_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    with pytest.raises(MappingClaimAuthorityError, match="signature|malformed|invalid"):
        approve_root_cause_mapping_claim(
            session,
            revision_id=ctx["source_revision_id"],
            entry=entry,
            source_locator=_MAPPING_SOURCE_LOCATOR,
            mapping_registry_version="root-cause-mapping@v1",
            approval_context=approval_ctx,
            curator_decision_token="forged.token.here",
        )


def test_deterministic_validate_node_persists_day6_binding(tmp_path: Path) -> None:
    from app.education_intelligence.fixtures import positive_cbse_item
    from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
    from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft, ResolvedScope
    from app.orchestration.enums import ReviewVerdictStatus
    from app.orchestration.fixtures import seed_day8_fixtures

    session = _session(tmp_path)
    ctx = seed_day8_fixtures(session)
    ctx = {**ctx, "subject_code": "mathematics"}
    service = build_orchestration_service(
        session,
        gateway=FakeGenerationGateway(),
        knowledge_adapter=FakeAnythingLLMAdapter(),
        memory_checkpointer=True,
        force_fake=True,
    )
    deps = service.dependencies
    canonical = positive_cbse_item(ctx)
    revision_id = ctx["official_revision_id"]
    draft = DraftQuestionItem(
        item_id=canonical.item_id,
        slot_index=0,
        stem_text=canonical.stem_text,
        options=[
            QuestionOptionDraft(option_key=o.option_key, text=o.text, is_correct=o.is_correct)
            for o in canonical.options
        ],
        source_revision_ids=[revision_id],
        learning_outcome_ids=list(canonical.learning_outcome_ids),
        competency_codes=list(canonical.competency_codes),
        declared_cognitive_level=canonical.declared_cognitive_level,
    )
    state: OrchestrationGraphState = {
        "run_id": "run-r19-day6",
        "request_hash": "hash-r19-day6",
        "request": OrchestrationRequest(
            idempotency_key="r19-day6-validate",
            curriculum_version_id=ctx["curriculum_version_id"],
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            grade_year_code="grade-8",
            subject_code="mathematics",
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            metadata_json={"learning_outcome_ids": list(canonical.learning_outcome_ids)},
        ).model_dump(mode="json"),
        "resolved_scope": ResolvedScope(
            curriculum_version_id=ctx["curriculum_version_id"],
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            grade_year_code="grade-8",
            medium_code="english",
            subject_code="mathematics",
        ).model_dump(mode="json"),
        "draft_items": [draft.model_dump(mode="json")],
        "solver_results": [],
        "review_verdicts": [
            {
                "reviewer": "fake",
                "item_id": draft.item_id,
                "status": ReviewVerdictStatus.PASS.value,
                "issue_codes": [],
                "field_paths": [],
                "evidence_refs": ["cite-r19"],
                "repair_instructions": [],
            }
        ],
        "knowledge_context": KnowledgeContextPack(
            query_id="r19",
            query_text="addition",
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            evidence=[
                {
                    "source_id": "00000000-0000-4000-8000-000000000099",
                    "source_revision_id": revision_id,
                    "source_revision_checksum": "a" * 64,
                    "binding_id": "bind-r19",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "official",
                    "locator": "loc",
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite-r19",
                }
            ],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
        "deterministic_validation": [],
        "node_attempts": {},
    }
    update = deterministic_validate_node(state, deps)
    summaries = update.get("deterministic_validation") or []
    assert len(summaries) == 1
    summary = summaries[0]
    assert not summary.get("blocking")
    assert summary.get("day6_validation_run_id")
    assert summary.get("input_hash")
    assert summary.get("learning_outcome_ids")
    assert summary.get("competency_codes")
    service.close()


def test_orchestration_hitl_day6_binding_and_root_cause_replay(tmp_path: Path) -> None:
    from app.orchestration.enums import OrchestrationRunStatus
    from app.orchestration.fixtures import (
        build_day8_test_service,
        build_diagnostic_orchestration_request,
    )

    session = _session(tmp_path)
    gateway = FakeGenerationGateway()
    ki_adapter = FakeAnythingLLMAdapter()
    _ctx, service = build_day8_test_service(session, gateway=gateway, memory_checkpointer=False)
    request = build_diagnostic_orchestration_request(
        _ctx,
        scenario="human_review",
        idempotency_key="d10-r19-hitl-day6-root-cause",
        requested_count=1,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "root_cause_enrichment_enabled": True,
                "deterministic_human_review_required": True,
            }
        }
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    checkpoint = service.compiled_graph.get_state(
        {"configurable": {"thread_id": completed.run_id}}
    )
    values = checkpoint.values or {}
    det = values.get("deterministic_validation") or []
    assert det and det[0].get("day6_validation_run_id")
    assert values.get("root_cause_results") is not None
    audit_session = service._control
    first_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    service.close()
    service2 = build_orchestration_service(
        session,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=False,
        force_fake=True,
    )
    replay = service2.run(request, resume=HumanResumeDecision(action="approve"))
    assert replay.run_id == completed.run_id
    second_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    assert second_count == first_count
    service2.close()
