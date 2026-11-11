from __future__ import annotations

from typing import Any

from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_MARKS_CORRECT,
    CANDIDATE_MARKS_INCORRECT,
    CANDIDATE_MARKS_UNATTEMPTED,
    CANDIDATE_PAPER1_TOTAL_MARKS,
)
from app.jee_main_exam_intelligence.contracts import PaperPlanSlot
from app.jee_main_exam_intelligence.enums import JeeMainQuestionTypeQuota


def build_scoring_preview(
    slots: list[PaperPlanSlot],
    *,
    marks_correct: float = CANDIDATE_MARKS_CORRECT,
    marks_incorrect: float = CANDIDATE_MARKS_INCORRECT,
    marks_unattempted: float = CANDIDATE_MARKS_UNATTEMPTED,
    expected_maximum: float | None = None,
) -> dict[str, Any]:
    mcq = sum(1 for s in slots if s.question_type == JeeMainQuestionTypeQuota.MCQ)
    numerical = sum(1 for s in slots if s.question_type == JeeMainQuestionTypeQuota.NUMERICAL)
    maximum = sum(
        (slot.marks if slot.marks is not None else marks_correct) for slot in slots
    )
    if expected_maximum is not None and slots:
        maximum = expected_maximum
    return {
        "item_count": len(slots),
        "maximum_marks": maximum if slots else (expected_maximum or CANDIDATE_PAPER1_TOTAL_MARKS),
        "marking_scheme": {
            "correct": marks_correct,
            "incorrect": marks_incorrect,
            "unattempted": marks_unattempted,
        },
        "mcq_slot_count": mcq,
        "numerical_slot_count": numerical,
    }
