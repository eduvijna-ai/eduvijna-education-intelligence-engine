from __future__ import annotations

from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticQuestionItem,
    DiagnosticQuestionOption,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService


def build_fixture_mcq_item(
    item_id: str = "diag-item-0",
    *,
    wrong_a: str = "11 off-by-one-low",
    wrong_b: str = "13 successor",
) -> DiagnosticQuestionItem:
    return DiagnosticQuestionItem(
        item_id=item_id,
        stem_text="Synthetic fixture: What is 7 + 5?",
        question_type="single_choice",
        options=[
            DiagnosticQuestionOption(option_key="A", text=wrong_a, is_correct=False),
            DiagnosticQuestionOption(option_key="B", text="12", is_correct=True),
            DiagnosticQuestionOption(option_key="C", text=wrong_b, is_correct=False),
        ],
        source_revision_ids=["00000000-0000-0000-0000-000000000001"],
        learning_outcome_ids=["lo-fixture-1"],
        competency_codes=["application"],
        metadata_json={"synthetic_fixture": True},
    )


def build_fixture_tags(item: DiagnosticQuestionItem) -> list[OptionDiagnosticTag]:
    tags: list[OptionDiagnosticTag] = []
    mapping = {
        "A": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        "B": None,
        "C": "MATH.ADD.WHOLE.SUM_AS_NEXT",
    }
    for option in item.options:
        tags.append(
            OptionDiagnosticTag(
                item_id=item.item_id,
                option_key=option.option_key,
                is_correct=option.is_correct,
                misconception_code=mapping.get(option.option_key),
                diagnostic_signal=(
                    "off-by-one-low"
                    if option.option_key == "A"
                    else "successor"
                    if option.option_key == "C"
                    else None
                ),
                evidence_refs=["[CIT-1]"],
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
                metadata_json={"option_text": option.text},
            )
        )
    return tags


def run_positive_fixture_validation(
    service: DiagnosticIntelligenceService,
    *,
    allowed_refs: list[str] | None = None,
) -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item()
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        learning_outcome_ids=["lo-fixture-1"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=allowed_refs or ["[CIT-1]"],
    )
    result = DistractorDiagnosticResult(
        item_id=item.item_id,
        question_type=item.question_type,
        option_tags=build_fixture_tags(item),
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        source_revision_ids=item.source_revision_ids,
    )
    candidate_codes = {
        c.misconception_code for c in resolve_misconception_candidates(request)
    }
    verdict = service.validate_result(
        request, result, candidate_codes=candidate_codes
    )
    assert verdict.status.value == "pass"
    return request
