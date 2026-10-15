from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
)
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_tags,
    run_positive_fixture_validation,
)
from app.diagnostic_intelligence.scope_guard import verify_day9_scope_guard
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy


def test_taxonomy_registry_loads() -> None:
    taxonomy = load_taxonomy()
    assert taxonomy.version == "misconception-taxonomy@v1"
    assert len(taxonomy.misconceptions) >= 3


def test_positive_fixture_distinct_misconceptions() -> None:
    service = DiagnosticIntelligenceService()
    run_positive_fixture_validation(service, allowed_refs=["[CIT-1]"])


def test_correct_option_cannot_carry_misconception() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item()
    tags = build_fixture_tags(item)
    tags[1] = tags[1].model_copy(update={"misconception_code": "MATH.ADD.WHOLE.SUM_AS_NEXT"})
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_evidence_refs=["[CIT-1]"],
    )
    result = DistractorDiagnosticResult(
        item_id=item.item_id,
        question_type=item.question_type,
        option_tags=tags,
    )
    verdict = service.validate_result(request, result)
    assert verdict.blocking is True
    assert "correct_option_mislabeled" in verdict.issue_codes


def test_day9_scope_guard_no_provider_imports() -> None:
    report = verify_day9_scope_guard()
    assert report["ok"] is True
