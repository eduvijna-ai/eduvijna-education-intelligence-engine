from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from day10_curator_auth import (
    DEFAULT_POLICY_CURATOR_SECRET,
    approve_mandatory_policy_with_curator,
    ensure_mandatory_policy_curator_credential,
    issue_mandatory_policy_approve_decision,
)
from day10_day6_binding import seed_production_day6_audit
from day10_source_lifecycle import (
    FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    default_board_mandatory_excerpt,
    ensure_board_mandatory_source_evidence,
    ensure_genuine_json_upload_source_approval,
    ensure_mapping_curator_admin_actor,
    mandatory_board_policy_rule,
)
from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    _day9_audit,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import _MAPPING_SOURCE_LOCATOR, _approve_revision_mapping_binding
from test_day10_r18_trust import (
    _apply_paper_with_day6_bindings,
    _approve_mandatory_policy_for_rule,
)

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.education_intelligence.fixtures import positive_cbse_item
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.models.education_intelligence import PolicyRegistryEntry, ValidationAuditRun
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceRevision
from app.models.tenancy import Institution
from app.orchestration.canonical_mapping import draft_to_canonical
from app.orchestration.contracts import (
    DraftQuestionItem,
    OrchestrationRequest,
    QuestionOptionDraft,
    ResolvedScope,
    ReviewVerdict,
)
from app.orchestration.control_session import open_control_session
from app.orchestration.enums import OrchestrationRunStatus, ReviewVerdictStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.nodes.root_cause import root_cause_enrich_node
from app.orchestration.nodes.validate import deterministic_validate_node
from app.orchestration.state import OrchestrationGraphState
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    MandatoryPolicyClaimAuthorityError,
    approve_mandatory_policy_claim,
)
from app.paper_distribution.target_policy_registry import (
    ensure_paper_target_policy_configured,
)
from app.prerequisite_intelligence.authority import load_revision_record
from app.root_cause_intelligence.enums import RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
)
from app.root_cause_intelligence.mapping_evidence import verify_revision_content_integrity
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def test_root_cause_analyze_split_sqlite_domain_and_control_sessions(tmp_path: Path) -> None:
    from test_day10_r8_trust import _load_snapshot, _root_cause_request

    domain = _session(tmp_path)
    ctx = _seed_production_institution_graph(domain)
    mapping_overlay = _approve_revision_mapping_binding(
        domain, tmp_path, ctx["source_revision_id"], ctx
    )
    domain.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000020"
    control = open_control_session(domain)
    _day9_audit(
        control,
        ctx,
        audit_id=audit_id,
        run_id="run-r20-split",
        request_hash="hash-r20-split",
        evidence_refs=["cite-r20"],
    )
    domain.commit()
    control.commit()
    snapshot = _load_snapshot(domain, ctx)
    from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext

    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    request = _root_cause_request(ctx, snapshot, institution_id=INST_A).model_copy(
        update={
            "orchestration_run_id": "run-r20-split",
            "orchestration_request_hash": "hash-r20-split",
            "day6_validation_run_id": ctx["day6_validation_run_id"],
            "day6_input_hash": ctx["day6_validated"]["input_hash"],
            "learning_outcome_ids": list(ctx["day6_validated"]["learning_outcome_ids"]),
            "competency_codes": list(ctx["day6_validated"]["competency_codes"]),
        }
    )
    result = RootCauseIntelligenceService().analyze(
        request,
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=control,
        domain_session=domain,
    )
    assert "domain_session" not in result.field_paths
    assert "control_session" not in result.field_paths
    assert result.verdict_status != RootCauseVerdictStatus.FAIL
    control.close()
    domain.close()


def test_root_cause_enrich_node_file_backed_sqlite_pass(tmp_path: Path) -> None:
    domain = _session(tmp_path)
    ctx = _seed_production_institution_graph(domain)
    mapping_overlay = _approve_revision_mapping_binding(
        domain, tmp_path, ctx["source_revision_id"], ctx
    )
    domain.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    domain.commit()
    service = build_orchestration_service(
        domain,
        gateway=FakeGenerationGateway(),
        knowledge_adapter=FakeAnythingLLMAdapter(),
        memory_checkpointer=True,
        force_fake=True,
    )
    deps = service.dependencies
    audit_id = "00000000-0000-4000-8000-000000000021"
    _day9_audit(
        deps.control_session,
        ctx,
        audit_id=audit_id,
        run_id="run-r20-node",
        request_hash="hash-r20-node",
        evidence_refs=["cite-r20-node"],
    )
    deps.control_session.commit()
    request = OrchestrationRequest(
        idempotency_key="r20-rc-node",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    state: OrchestrationGraphState = {
        "run_id": "run-r20-node",
        "request_hash": "hash-r20-node",
        "request": request.model_dump(mode="json"),
        "root_cause_results": [],
        "diagnostic_validation": [{"item_id": "item-r8", "blocking": False}],
        "diagnostic_results": [
            {
                "item_id": "item-r8",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "audit_refs": [audit_id],
                "option_tags": [
                    {
                        "option_key": "A",
                        "is_correct": False,
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": ["cite-r20-node"],
                    }
                ],
            }
        ],
        "resolved_scope": {
            "curriculum_version_id": ctx["curriculum_version_id"],
            "organization_id": ctx["organization_id"],
            "institution_id": ctx["institution_id"],
            "grade_year_code": "grade-4",
            "subject_code": "mathematics",
            "concept_codes": ["multi-step-addition"],
        },
        "draft_items": [
            {
                "item_id": "item-r8",
                "concept_codes": ["multi-step-addition"],
                "source_revision_ids": [ctx["source_revision_id"]],
            }
        ],
        "deterministic_validation": [
            {
                "item_id": "item-r8",
                "blocking": False,
                "day6_validation_run_id": ctx["day6_validation_run_id"],
                "input_hash": ctx["day6_validated"]["input_hash"],
                "learning_outcome_ids": list(ctx["day6_validated"]["learning_outcome_ids"]),
                "competency_codes": list(ctx["day6_validated"]["competency_codes"]),
            }
        ],
        "knowledge_context": KnowledgeContextPack(
            query_id="r20",
            query_text="addition",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[
                {
                    "source_id": ctx["source_id"],
                    "source_revision_id": ctx["source_revision_id"],
                    "source_revision_checksum": "a" * 64,
                    "binding_id": "bind-r20",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "official",
                    "locator": "loc",
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite-r20-node",
                }
            ],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
        "node_attempts": {},
    }
    update = root_cause_enrich_node(state, deps)
    results = update.get("root_cause_results") or []
    assert len(results) == 1
    assert results[0].get("verdict_status") == RootCauseVerdictStatus.PASS.value
    assert results[0].get("hypotheses")
    item_audits = deps.control_session.scalars(
        select(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "root_cause_item",
            OrchestrationAuditEvent.status == "pass",
        )
    ).all()
    assert item_audits
    service.close()


def test_day6_revalidate_when_canonical_hash_changes_with_same_stem(tmp_path: Path) -> None:
    from app.orchestration.fixtures import seed_day8_fixtures

    domain = _session(tmp_path)
    ctx = seed_day8_fixtures(domain)
    ctx = {**ctx, "subject_code": "mathematics"}
    service = build_orchestration_service(
        domain,
        gateway=FakeGenerationGateway(),
        knowledge_adapter=FakeAnythingLLMAdapter(),
        memory_checkpointer=False,
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
            QuestionOptionDraft(
                option_key=o.option_key, text=o.text, is_correct=o.is_correct
            )
            for o in canonical.options
        ],
        source_revision_ids=[revision_id],
        learning_outcome_ids=list(canonical.learning_outcome_ids),
        competency_codes=list(canonical.competency_codes),
        declared_cognitive_level=canonical.declared_cognitive_level,
    )
    scope = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-8",
        medium_code="english",
        subject_code="mathematics",
    )
    base_state: OrchestrationGraphState = {
        "run_id": "run-r20-day6",
        "request_hash": "hash-r20-day6",
        "request": OrchestrationRequest(
            idempotency_key="r20-day6",
            curriculum_version_id=ctx["curriculum_version_id"],
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            grade_year_code="grade-8",
            subject_code="mathematics",
            retrieval_profile_version="default@v1",
        ).model_dump(mode="json"),
        "resolved_scope": scope.model_dump(mode="json"),
        "draft_items": [draft.model_dump(mode="json")],
        "solver_results": [],
        "review_verdicts": [
            ReviewVerdict(
                reviewer="fake",
                item_id=draft.item_id,
                status=ReviewVerdictStatus.PASS,
                issue_codes=[],
                field_paths=[],
                evidence_refs=["cite-r20-day6"],
                repair_instructions=[],
            ).model_dump(mode="json")
        ],
        "knowledge_context": KnowledgeContextPack(
            query_id="r20-day6",
            query_text="math",
            retrieval_profile_version="default@v1",
            evidence=[
                {
                    "source_id": "00000000-0000-4000-8000-000000000099",
                    "source_revision_id": revision_id,
                    "source_revision_checksum": "a" * 64,
                    "binding_id": "bind",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "t",
                    "locator": "loc",
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite-r20-day6",
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
    first = deterministic_validate_node(base_state, deps)
    first_summary = (first.get("deterministic_validation") or [])[0]
    first_run_id = first_summary.get("day6_validation_run_id")
    first_hash = first_summary.get("input_hash")
    assert first_run_id and first_hash

    flipped = draft.model_copy(
        update={
            "options": [
                QuestionOptionDraft(option_key="A", text="opt A", is_correct=False),
                QuestionOptionDraft(option_key="B", text="opt B", is_correct=True),
            ],
            "competency_codes": ["application"],
        }
    )
    second_state = {
        **base_state,
        "draft_items": [flipped.model_dump(mode="json")],
        "deterministic_validation": [first_summary],
    }
    second = deterministic_validate_node(second_state, deps)
    second_summary = (second.get("deterministic_validation") or [])[0]
    assert second_summary.get("day6_validation_run_id") != first_run_id
    assert second_summary.get("input_hash") != first_hash
    run_count = domain.scalar(select(func.count()).select_from(ValidationAuditRun))
    assert run_count == 2
    service.close()


def test_day6_validate_retry_reuses_persisted_run_without_duplicate(tmp_path: Path) -> None:
    from app.orchestration.fixtures import seed_day8_fixtures

    domain = _session(tmp_path)
    ctx = seed_day8_fixtures(domain)
    ctx = {**ctx, "subject_code": "mathematics"}
    scope = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-8",
        medium_code="english",
        subject_code="mathematics",
    )
    canonical = positive_cbse_item(ctx)
    revision_id = ctx["official_revision_id"]
    draft = DraftQuestionItem(
        item_id=canonical.item_id,
        slot_index=0,
        stem_text=canonical.stem_text,
        options=[
            QuestionOptionDraft(
                option_key=o.option_key, text=o.text, is_correct=o.is_correct
            )
            for o in canonical.options
        ],
        source_revision_ids=[revision_id],
        learning_outcome_ids=list(canonical.learning_outcome_ids),
        competency_codes=list(canonical.competency_codes),
        declared_cognitive_level=canonical.declared_cognitive_level,
        declared_difficulty=canonical.declared_difficulty,
        metadata_json=dict(canonical.metadata_json or {}),
    )
    canonical_hash = draft_to_canonical(draft, scope, request_marks=None).canonical_hash()
    run_id, _validated = seed_production_day6_audit(
        domain,
        item_id=draft.item_id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        curriculum_version_id=ctx["curriculum_version_id"],
        input_hash=canonical_hash,
        grade_year_code="grade-8",
        learning_outcome_id=ctx["learning_outcome_id"],
        competency_codes=list(canonical.competency_codes),
        declared_cognitive_level=str(canonical.declared_cognitive_level or "apply").lower(),
    )
    domain.commit()
    before = domain.scalar(select(func.count()).select_from(ValidationAuditRun))
    service = build_orchestration_service(
        domain,
        gateway=FakeGenerationGateway(),
        knowledge_adapter=FakeAnythingLLMAdapter(),
        memory_checkpointer=False,
        force_fake=True,
    )
    deps = service.dependencies
    state: OrchestrationGraphState = {
        "run_id": "run-r20-idem",
        "request_hash": "hash-r20-idem",
        "request": OrchestrationRequest(
            idempotency_key="r20-idem",
            curriculum_version_id=ctx["curriculum_version_id"],
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            grade_year_code="grade-8",
            subject_code="mathematics",
            retrieval_profile_version="default@v1",
        ).model_dump(mode="json"),
        "resolved_scope": scope.model_dump(mode="json"),
        "draft_items": [draft.model_dump(mode="json")],
        "solver_results": [],
        "review_verdicts": [
            ReviewVerdict(
                reviewer="fake",
                item_id=draft.item_id,
                status=ReviewVerdictStatus.PASS,
                issue_codes=[],
                field_paths=[],
                evidence_refs=["cite"],
                repair_instructions=[],
            ).model_dump(mode="json")
        ],
        "knowledge_context": KnowledgeContextPack(
            query_id="idem",
            query_text="x",
            retrieval_profile_version="default@v1",
            evidence=[
                {
                    "source_id": "00000000-0000-4000-8000-000000000099",
                    "source_revision_id": revision_id,
                    "source_revision_checksum": "a" * 64,
                    "binding_id": "bind",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "t",
                    "locator": "loc",
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite",
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
    summary_row = (update.get("deterministic_validation") or [])[0]
    assert summary_row.get("input_hash") == canonical_hash
    assert summary_row.get("day6_validation_run_id") == run_id
    after = domain.scalar(select(func.count()).select_from(ValidationAuditRun))
    assert after == before
    service.close()


def test_json_upload_manual_metadata_injection_does_not_bypass_storage_integrity(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
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
    revision.metadata_json = {
        **(revision.metadata_json or {}),
        "manual_metadata": {
            "locator": _MAPPING_SOURCE_LOCATOR,
            "excerpt": "forged",
        },
    }
    session.flush()
    record = load_revision_record(session, revision.id)
    assert record is not None
    assert revision.storage_path
    stored_file = Path(storage_root) / revision.storage_path
    stored_file.write_bytes(stored_file.read_bytes() + b"corrupt")
    assert not verify_revision_content_integrity(session, record, storage_root=storage_root)


def test_mandatory_policy_claim_requires_rule_binding_and_actor(tmp_path: Path) -> None:

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
    session.flush()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    session.flush()
    actor_id = "founder-day10-trust"
    admin = ensure_mapping_curator_admin_actor(
        session,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        external_code=actor_id,
        display_name="Day10 policy curator",
    )
    ensure_mandatory_policy_curator_credential(
        session,
        admin,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        board_code=str(rule.scope_code),
        board_scope_authorized=True,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="not bound"):
        approve_mandatory_policy_claim(
            session,
            rule_id=str(rule.id),
            revision_id=str(uuid4()),
            scope_type=str(rule.scope_type),
            scope_code=str(rule.scope_code),
            policy_key=str(rule.policy_key),
            value_json=dict(rule.value_json or {}),
            actor_id=actor_id,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curator_decision_token="invalid",
        )
    from app.paper_distribution.mandatory_policy_claim_authority import (
        _policy_value_checksum,
        _rule_lifecycle_digest,
    )

    valid_token = issue_mandatory_policy_approve_decision(
        session,
        admin_external_code=actor_id,
        operator_secret=DEFAULT_POLICY_CURATOR_SECRET,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        rule=rule,
        revision_id=revision.id,
        value_checksum=_policy_value_checksum(dict(rule.value_json or {})),
        rule_lifecycle_digest=_rule_lifecycle_digest(rule),
    )
    with pytest.raises(MandatoryPolicyClaimAuthorityError, match="actor mismatch"):
        approve_mandatory_policy_claim(
            session,
            rule_id=str(rule.id),
            revision_id=revision.id,
            scope_type=str(rule.scope_type),
            scope_code=str(rule.scope_code),
            policy_key=str(rule.policy_key),
            value_json=dict(rule.value_json or {}),
            actor_id="random-actor",
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curator_decision_token=valid_token,
        )
    claim_id = approve_mandatory_policy_with_curator(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        actor_id=actor_id,
        policy_curator_secret=DEFAULT_POLICY_CURATOR_SECRET,
    )
    assert claim_id


def test_board_mandatory_apply40_paper_pass_fail_after_claim_gate(tmp_path: Path) -> None:

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
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    rule = mandatory_board_policy_rule(
        value_json={"mandatory_cognitive_exact_percent": {"apply": 40.0}},
        source_locator=FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    )
    session.add(rule)
    session.flush()
    revision.policy_rules.append(rule)
    _approve_mandatory_policy_for_rule(
        session,
        rule=rule,
        revision_id=revision.id,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    ensure_paper_target_policy_configured(session)
    session.commit()
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


def test_orchestration_hitl_file_backed_replay_idempotent(tmp_path: Path) -> None:
    domain = _session(tmp_path)
    ctx, service = build_day8_test_service(domain, memory_checkpointer=False)
    request = build_diagnostic_orchestration_request(
        ctx,
        scenario="human_review",
        idempotency_key="d10-r20-hitl-root-cause",
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
    attempts = (checkpoint.values or {}).get("node_attempts") or {}
    assert "root_cause_enrich" in attempts
    audit_session = service._control
    first_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    service.close()
    service2 = build_orchestration_service(
        domain,
        gateway=FakeGenerationGateway(),
        knowledge_adapter=FakeAnythingLLMAdapter(),
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
