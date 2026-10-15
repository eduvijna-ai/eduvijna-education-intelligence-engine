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
        competency_codes=["application"],
        learning_outcome_ids=["lo-fixture-1"],
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


def test_missing_definition_topic_rejected_for_scoped_request() -> None:
    service = DiagnosticIntelligenceService()
    request = _request(topic_codes=["algebra"])
    candidates = {c.misconception_code for c in resolve_misconception_candidates(request)}
    assert "MATH.ADD.WHOLE.OFF_BY_ONE_LOW" not in candidates
    tags = build_fixture_tags(request.item)
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=tags,
    )
    verdict = service.validate_result(request, result, candidate_codes=candidates)
    assert verdict.review_required or verdict.blocking


def test_explicit_broad_scope_allows_lo_mismatch() -> None:
    request = _request(learning_outcome_ids=["lo-out-of-band"])
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    assert "MATH.ADD.BROAD.EXPLICIT_WILDCARD" in codes


def test_wrong_grade_excludes_candidates() -> None:
    request = _request(grade_year_code="grade-1")
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    assert "MATH.ADD.WHOLE.OFF_BY_ONE_LOW" not in codes


def test_wrong_subject_excludes_candidates() -> None:
    request = _request(subject_code="physics")
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    assert "MATH.ADD.WHOLE.OFF_BY_ONE_LOW" not in codes


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


def test_tenant_revision_evidence_rejected() -> None:
    service = DiagnosticIntelligenceService()
    request = _request(allowed_source_revision_ids=["00000000-0000-0000-0000-000000000001"])
    candidates = {c.misconception_code for c in resolve_misconception_candidates(request)}
    wrong = request.item.options[0]
    tag = OptionDiagnosticTag(
        item_id=request.item.item_id,
        option_key=wrong.option_key,
        is_correct=False,
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        diagnostic_signal="off-by-one-low",
        evidence_refs=["00000000-0000-0000-0000-000000000099"],
        metadata_json={"option_text": "11 off-by-one-low"},
    )
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=[tag],
    )
    verdict = service.validate_result(request, result, candidate_codes=candidates)
    assert "tenant_evidence_mismatch" in verdict.issue_codes
