from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.request_capture import RequestCapturingGateway
from app.orchestration.human_decision import HumanResumeDecision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _stem_item(stem: str, item_id: str = "arith-1") -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item(item_id=item_id).model_copy(update={"stem_text": stem})
    return DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        competency_codes=["application"],
        learning_outcome_ids=["lo-fixture-1"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )


def _validate_tags(
    service: DiagnosticIntelligenceService,
    request: DiagnosticAuthoringRequest,
    tags: list,
) -> object:
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    return service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=codes,
    )


def test_arithmetic_signal_service_positive_7_plus_5() -> None:
    service = DiagnosticIntelligenceService()
    request = _stem_item("Synthetic fixture: What is 7 + 5?")
    tags = build_fixture_tags(request.item)
    assert _validate_tags(service, request, tags).status.value == "pass"


def test_arithmetic_signal_service_negative_8_plus_5_off_by_one() -> None:
    service = DiagnosticIntelligenceService()
    request = _stem_item("Synthetic fixture: What is 8 + 5?", item_id="arith-8-5")
    tags = build_fixture_tags(request.item)
    verdict = _validate_tags(service, request, tags)
    assert verdict.status.value != "pass"
    assert "signal_text_mismatch" in verdict.issue_codes


def test_arithmetic_signal_service_negative_8_plus_5_sum_as_next() -> None:
    service = DiagnosticIntelligenceService()
    request = _stem_item("Synthetic fixture: What is 8 + 5?", item_id="arith-8-5-next")
    tags = build_fixture_tags(request.item)
    tags[2] = tags[2].model_copy(update={"misconception_code": "MATH.ADD.WHOLE.SUM_AS_NEXT"})
    tags[2].metadata_json["option_text"] = "13 successor"
    verdict = _validate_tags(service, request, tags)
    assert verdict.status.value != "pass"
    assert "signal_text_mismatch" in verdict.issue_codes


def test_broad_policy_decorative_label_does_not_pass() -> None:
    service = DiagnosticIntelligenceService()
    request = _stem_item("Synthetic fixture: What is 7 + 5?", item_id="broad-1")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={
            "misconception_code": "MATH.ADD.BROAD.EXPLICIT_WILDCARD",
            "diagnostic_signal": "broad-policy",
        }
    )
    options = list(request.item.options)
    options[0] = options[0].model_copy(update={"text": "10 broad-policy"})
    request = request.model_copy(
        update={"item": request.item.model_copy(update={"options": options})}
    )
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)} | {
        "MATH.ADD.BROAD.EXPLICIT_WILDCARD"
    }
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=codes,
    )
    assert verdict.status.value != "pass"
    assert "signal_text_mismatch" in verdict.issue_codes


def test_source_authorization_empty_allowed_list_fails() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="src-auth")
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_evidence_refs=["[CIT-1]"],
        allowed_source_revision_ids=[],
    )
    tags = build_fixture_tags(item)
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert "source_authorization_unresolved" in verdict.issue_codes


def test_hitl_marks_edit_forbidden() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx,
        scenario="human_review",
        idempotency_key="day9-r6-marks-edit",
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    item_id = paused.metadata_json["interrupt_payload"]["item_ids"][0]
    failed = service.run(
        request,
        resume=HumanResumeDecision(action="edit", item_patches={item_id: {"marks": 99.0}}),
    )
    assert failed.status == OrchestrationRunStatus.FAILED
    assert "human_edit_provenance_forbidden" in failed.errors
    session.close()


def test_foreign_injection_not_in_knowledge_context_or_author_payload() -> None:
    session = _session()
    gateway = RequestCapturingGateway(FakeGenerationGateway())
    ctx, service = build_day8_test_service(session, gateway=gateway)
    from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions

    foreign = seed_day9_foreign_tenant_revisions(session, ctx)
    foreign_id = foreign.foreign_organization_revision_id
    malicious = build_orchestration_request(
        ctx,
        scenario="injection_evidence",
        idempotency_key="day9-r6-inj-proof",
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
    bounded = str(knowledge.get("bounded_text") or "")
    assert foreign_id not in evidence_ids
    assert foreign_id not in bounded
    author_calls = gateway.captured_for_role(GenerationNodeRole.AUTHOR)
    assert author_calls
    for captured in author_calls:
        payload = json.dumps(captured.user_payload, default=str)
        assert foreign_id not in payload
        assert "DAY9-ORG-B" not in payload
    if result.status == OrchestrationRunStatus.COMPLETED:
        assert all(item.marks == 1.0 for item in result.items)
        for item in result.items:
            assert foreign_id not in item.source_revision_ids
    session.close()
