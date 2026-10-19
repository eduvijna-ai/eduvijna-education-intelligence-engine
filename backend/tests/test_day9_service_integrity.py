from __future__ import annotations

from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
    with_fixture_day7_evidence,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService


def _request() -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item(item_id="integrity-1")
    return with_fixture_day7_evidence(
        DiagnosticAuthoringRequest(
            item=item,
            subject_code="mathematics",
            grade_year_code="grade-8",
            topic_codes=["whole-numbers"],
            concept_codes=["addition-whole"],
            learning_outcome_ids=["lo-fixture-1"],
            competency_codes=["application"],
            allowed_evidence_refs=["[CIT-1]"],
            allowed_source_revision_ids=item.source_revision_ids,
        )
    )


def _codes(request: DiagnosticAuthoringRequest) -> set[str]:
    return {c.misconception_code for c in resolve_misconception_candidates(request)}


def test_empty_option_tags_cannot_pass() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, []),
        candidate_codes=_codes(request),
    )
    assert verdict.status.value != "pass"
    assert (
        "empty_option_tags" in verdict.issue_codes
        or "missing_option_tags" in verdict.issue_codes
    )


def test_partial_and_duplicate_tags_rejected() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    partial = service.validate_result(
        request,
        build_fixture_result(request.item, build_fixture_tags(request.item)[:2]),
        candidate_codes=_codes(request),
    )
    assert partial.blocking is True
    assert "missing_option_tags" in partial.issue_codes

    tags = build_fixture_tags(request.item)
    dup = tags + [tags[0].model_copy()]
    duplicate = service.validate_result(
        request,
        build_fixture_result(request.item, dup),
        candidate_codes=_codes(request),
    )
    assert "duplicate_option_tag_key" in duplicate.issue_codes


def test_item_and_type_mismatch_blocked() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    tags = build_fixture_tags(request.item)
    wrong_item = service.validate_result(
        request,
        build_fixture_result(request.item, tags).model_copy(update={"item_id": "other-item"}),
        candidate_codes=_codes(request),
    )
    assert "result_item_id_mismatch" in wrong_item.issue_codes

    wrong_type = service.validate_result(
        request,
        build_fixture_result(request.item, tags).model_copy(
            update={"question_type": "short_answer"}
        ),
        candidate_codes=_codes(request),
    )
    assert "result_question_type_mismatch" in wrong_type.issue_codes


def test_canonical_correctness_and_metadata_text_not_authoritative() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    tags = build_fixture_tags(request.item)
    tags[1] = tags[1].model_copy(update={"is_correct": False, "misconception_code": None})
    mislabeled = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert "correct_option_mislabeled" in mislabeled.issue_codes

    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={
            "metadata_json": {
                "option_text": "12",
            }
        }
    )
    forged_meta = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert "untrusted_option_text_metadata" in forged_meta.issue_codes
    assert "second_correct_distractor" not in forged_meta.issue_codes


def test_genuine_passing_tags() -> None:
    service = DiagnosticIntelligenceService()
    request = _request()
    tags = build_fixture_tags(request.item)
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert verdict.status.value == "pass"
