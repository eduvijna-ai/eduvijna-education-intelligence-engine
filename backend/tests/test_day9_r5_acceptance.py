from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.validators.signal import validate_signal_alignment
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_foreign_injection_metadata_does_not_bypass_day7_retrieval() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions

    foreign = seed_day9_foreign_tenant_revisions(session, ctx)
    foreign_id = foreign.foreign_organization_revision_id
    malicious = build_orchestration_request(
        ctx,
        scenario="injection_evidence",
        idempotency_key="day9-r5-inj-bypass",
    )
    malicious = malicious.model_copy(
        update={
            "metadata_json": {
                **malicious.metadata_json,
                "injection_revision_id": foreign_id,
            },
        }
    )
    result = service.run(malicious)
    state = service.compiled_graph.get_state(
        {"configurable": {"thread_id": result.run_id}}
    )
    knowledge = state.values.get("knowledge_context") or {}
    evidence_ids = {
        str(entry.get("source_revision_id"))
        for entry in knowledge.get("evidence") or []
        if entry.get("source_revision_id")
    }
    assert foreign_id not in evidence_ids
    assert foreign_id not in str(knowledge.get("bounded_text") or "")
    session.close()


def test_signal_misleading_decorator_words_fail_arithmetic() -> None:
    stem = "Synthetic fixture: What is 7 + 5?"
    for option_text in ("7 successor", "5 off-by-one-low", "17 successor"):
        issues = validate_signal_alignment(
            OptionDiagnosticTag(
                item_id="x",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            ),
            option_text,
            stem_text=stem,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        )
        assert "signal_text_mismatch" in issues
    off_low = validate_signal_alignment(
        OptionDiagnosticTag(
            item_id="x",
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        ),
        "11 off-by-one-low",
        stem_text=stem,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
    )
    assert not off_low
    assert not validate_signal_alignment(
        OptionDiagnosticTag(
            item_id="x",
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        ),
        "13 successor",
        stem_text=stem,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
    )


def test_result_source_provenance_fail_closed() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="prov-r5")
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    tags = build_fixture_tags(item)
    codes = {"MATH.ADD.WHOLE.OFF_BY_ONE_LOW", "MATH.ADD.WHOLE.SUM_AS_NEXT"}

    missing = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=[],
        ),
        candidate_codes=codes,
    )
    assert "result_source_revision_missing" in missing.issue_codes

    mismatch = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=["FOREIGN-REVISION"],
        ),
        candidate_codes=codes,
    )
    assert "result_source_revision_mismatch" in mismatch.issue_codes

    empty_allowed_request = request.model_copy(update={"allowed_source_revision_ids": []})
    verdict_empty = service.validate_result(
        empty_allowed_request,
        build_fixture_result(item, tags),
        candidate_codes=codes,
    )
    assert "source_authorization_unresolved" in verdict_empty.issue_codes

    ok = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=list(item.source_revision_ids),
        ),
        candidate_codes=codes,
    )
    assert ok.status.value == "pass"


def test_distinctness_rejects_metadata_only_option_text() -> None:
    from app.diagnostic_intelligence.validators.distinctness import validate_distinctness

    tags = [
        OptionDiagnosticTag(
            item_id="x",
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            metadata_json={"option_text": "dup"},
        ),
        OptionDiagnosticTag(
            item_id="x",
            option_key="C",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
            metadata_json={"option_text": "dup"},
        ),
    ]
    issues, _ = validate_distinctness("x", tags, canonical_text_by_key={})
    assert "canonical_option_text_missing" in issues


def test_diagnostic_hitl_edit_revalidates_diagnostics() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-r5-hitl-edit",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    mid = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert mid.status == OrchestrationRunStatus.REVIEW_REQUIRED
    payload = mid.metadata_json.get("interrupt_payload") or {}
    item_id = payload["item_ids"][0]
    calls_before = len(
        [c for c in gateway.call_history() if c.call_context.role == GenerationNodeRole.DIAGNOSTIC]
    )
    edited = service.run(
        request,
        resume=HumanResumeDecision(
            action="edit",
            item_patches={
                item_id: {
                    "stem_text": (
                        "Synthetic number-sense fixture: choose the best edited statement."
                    ),
                },
            },
        ),
    )
    assert edited.status == OrchestrationRunStatus.REVIEW_REQUIRED
    after_edit_payload = edited.metadata_json.get("interrupt_payload") or {}
    assert not after_edit_payload.get("diagnostic_results")
    revalidated = service.run(request, resume=HumanResumeDecision(action="approve"))
    calls_after_revalidate = len(
        [c for c in gateway.call_history() if c.call_context.role == GenerationNodeRole.DIAGNOSTIC]
    )
    assert calls_after_revalidate > calls_before
    completed = revalidated
    if completed.status == OrchestrationRunStatus.REVIEW_REQUIRED:
        completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED
    session.close()


def test_day7_retrieval_returns_in_scope_injection_revision() -> None:
    session = _session()
    from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
    from app.knowledge_intelligence.service import KnowledgeIntelligenceService
    from app.orchestration.fixtures import seed_day8_fixtures

    adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=adapter)
    ki = KnowledgeIntelligenceService(session, adapter)
    result = ki.retrieve(
        KnowledgeRetrievalRequest(
            query_text="ignore previous instructions completing square",
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curriculum_version_id=ctx["curriculum_version_id"],
            grade_year_code="grade-8",
            medium_code="english",
            subject_code="mathematics",
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )
    ids = {item.source_revision_id for item in result.items}
    assert ctx["injection_revision_id"] in ids
    session.close()
