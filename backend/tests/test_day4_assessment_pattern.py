from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.curriculum_intelligence.assessment import extract_assessment_pattern
from app.schemas.assessment_pattern import AssessmentPattern, AssessmentSection
from app.schemas.curriculum_intelligence import AssessmentEvidenceInput


@pytest.mark.parametrize("partial_summary", [False, True])
def test_explicit_assessment_instructions_have_typed_structure(partial_summary: bool) -> None:
    pattern = extract_assessment_pattern(
        "Maximum Marks: 10 Time Allowed: 30 minutes. This paper contains 4 questions. "
        "Section A contains 2 MCQ questions carrying 1 mark each. "
        "Section B has 2 long answer questions carrying 4 marks each."
        + (" SECTION A (2 x 1 = 2)" if partial_summary else ""),
        source_locator="Synthetic PDF page 1",
    )
    assert pattern.status == "verified"
    assert pattern.total_marks == 10
    assert pattern.duration_minutes == 30
    assert pattern.total_questions == 4
    assert [section.maximum_marks for section in pattern.sections] == [2, 8]
    assert pattern.sections[0].categories[0].code == "multiple_choice"
    assert pattern.sections[1].categories[0].code == "long_answer"


def test_missing_or_inconsistent_patterns_stay_review_required() -> None:
    empty = extract_assessment_pattern("Official index only", source_locator="index")
    assert empty.status == "review_required" and empty.total_marks is None
    inconsistent = extract_assessment_pattern(
        "Max Marks: 80 Time: 3 hours. Section A has 2 MCQs carrying 1 mark each.",
        source_locator="Synthetic source",
    )
    assert inconsistent.status == "review_required"
    assert inconsistent.total_marks == 80
    assert inconsistent.sections == []
    assert inconsistent.unresolved_items


def test_typed_assessment_rejects_bad_totals_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="paper total"):
        AssessmentPattern(
            status="verified",
            total_marks=80,
            source_locator="test",
            sections=[
                AssessmentSection(code="A", title="A", maximum_marks=20, source_locator="test")
            ],
        )
    with pytest.raises(ValidationError):
        AssessmentEvidenceInput(
            curriculum_version_id="18ed948d-4ba5-4f4d-a97d-cba9fb3de3a7",
            source_revision_id="60db499d-ac43-4d76-9f08-7d79a49bdff5",
            evidence_type="assessment_pattern",
            evidence_json={"invented": "untyped"},
        )
    with pytest.raises(ValidationError, match="section codes"):
        AssessmentPattern(
            status="partial",
            source_locator="test",
            sections=[
                AssessmentSection(code="A", title="A", source_locator="test"),
                AssessmentSection(code="A", title="Duplicate A", source_locator="test"),
            ],
        )
