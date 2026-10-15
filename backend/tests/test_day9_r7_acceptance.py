from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.diagnostic_intelligence.fixtures import build_fixture_mcq_item, build_fixture_tags
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.orchestration.day9_tenant_fixtures import Day9ForeignTenantContext
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.request_capture import RequestCapturingGateway


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_sourceless_item_rejects_forged_result_source_revisions() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="sourceless-r7").model_copy(
        update={"source_revision_ids": []}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[],
        allowed_evidence_refs=["[CIT-1]"],
    )
    tags = build_fixture_tags(item)
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}

    ok = service.validate_result(
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
    assert ok.status.value == "pass"
    assert not ok.blocking

    forged = service.validate_result(
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
    assert forged.status.value != "pass"
    assert forged.blocking
    assert "result_source_revision_mismatch" in forged.issue_codes
    assert "malformed_model_output" in forged.issue_codes


def _assert_no_foreign_leak(
    *,
    foreign_id: str,
    content_marker: str,
    knowledge: dict,
    capturing: RequestCapturingGateway,
    result: object,
) -> None:
    evidence_ids = {
        str(entry.get("source_revision_id"))
        for entry in knowledge.get("evidence") or []
        if entry.get("source_revision_id")
    }
    bounded = str(knowledge.get("bounded_text") or "")
    assert foreign_id not in evidence_ids
    assert foreign_id not in bounded
    assert content_marker not in bounded

    author_calls = capturing.captured_for_role(GenerationNodeRole.AUTHOR)
    assert author_calls, "author generate() must be invoked"
    for captured in author_calls:
        blob = json.dumps(captured.user_payload, default=str)
        assert foreign_id not in blob
        assert content_marker not in blob
        assert foreign_id not in captured.system_prompt
        assert content_marker not in captured.system_prompt

    curriculum_calls = capturing.captured_for_role(GenerationNodeRole.CURRICULUM_REVIEW)
    assert curriculum_calls, "curriculum reviewer generate() must be invoked"
    for captured in curriculum_calls:
        blob = json.dumps(captured.user_payload, default=str)
        assert foreign_id not in blob
        assert content_marker not in blob

    status = getattr(result, "status", None)
    if status == OrchestrationRunStatus.COMPLETED:
        for item in getattr(result, "items", []) or []:
            assert foreign_id not in item.source_revision_ids
        metadata = getattr(result, "metadata_json", {}) or {}
        for entry in metadata.get("diagnostic_results") or []:
            for tag in entry.get("option_tags") or []:
                for ref in tag.get("evidence_refs") or []:
                    assert foreign_id not in str(ref)


def test_foreign_injection_absent_from_captured_generation_requests() -> None:
    session = _session()
    inner = FakeGenerationGateway()
    capturing = RequestCapturingGateway(inner)
    ctx, service = build_day8_test_service(session, gateway=capturing)
    from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions

    foreign: Day9ForeignTenantContext = seed_day9_foreign_tenant_revisions(session, ctx)
    cases = [
        (foreign.foreign_organization_revision_id, "DAY9-ORG-B"),
        (foreign.foreign_institution_revision_id, "DAY9-INST-B"),
        (foreign.foreign_teacher_revision_id, "DAY9-TEACHER-B"),
    ]
    for foreign_id, marker in cases:
        malicious = build_orchestration_request(
            ctx,
            scenario="injection_evidence",
            idempotency_key=f"day9-r7-inj-{marker}",
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
        _assert_no_foreign_leak(
            foreign_id=foreign_id,
            content_marker=marker,
            knowledge=knowledge,
            capturing=capturing,
            result=result,
        )
        if result.status == OrchestrationRunStatus.COMPLETED:
            assert all(item.marks == 1.0 for item in result.items)
    session.close()
