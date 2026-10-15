from __future__ import annotations

from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.fixtures import build_fixture_mcq_item, build_fixture_tags
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService


def _request(**kwargs: object) -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item()
    base = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_evidence_refs=["[CIT-1]"],
    )
    return base.model_copy(update=kwargs)


def test_non_candidate_code_rejected() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    candidates = {c.misconception_code for c in resolve_misconception_candidates(request)}
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(update={"misconception_code": "MATH.ADD.ALGEBRA_TOPIC_ONLY"})
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=tags,
    )
    verdict = service.validate_result(request, result, candidate_codes=candidates)
    assert "non_candidate_misconception" in verdict.issue_codes


def test_wrong_topic_misconception_rejected() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    candidates = {c.misconception_code for c in resolve_misconception_candidates(request)}
    candidates.add("MATH.ADD.ALGEBRA_TOPIC_ONLY")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={
            "misconception_code": "MATH.ADD.ALGEBRA_TOPIC_ONLY",
            "diagnostic_signal": "algebra",
        }
    )
    tags[0].metadata_json["option_text"] = "algebra mistake"
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=tags,
    )
    verdict = service.validate_result(request, result, candidate_codes=candidates)
    assert "curriculum_scope_mismatch" in verdict.issue_codes


def test_fake_signal_not_in_taxonomy_rejected() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    candidates = {c.misconception_code for c in resolve_misconception_candidates(request)}
    wrong = request.item.options[0]
    tag = OptionDiagnosticTag(
        item_id=request.item.item_id,
        option_key=wrong.option_key,
        is_correct=False,
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        diagnostic_signal="convenient-fake-signal",
        metadata_json={"option_text": "convenient-fake-signal in text"},
    )
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=[tag],
    )
    verdict = service.validate_result(request, result, candidate_codes=candidates)
    assert "signal_text_mismatch" in verdict.issue_codes
