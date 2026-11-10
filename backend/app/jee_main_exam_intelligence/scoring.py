from __future__ import annotations

from typing import Any

from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_MARKS_CORRECT,
    CANDIDATE_MARKS_INCORRECT,
    CANDIDATE_MARKS_UNATTEMPTED,
    CANDIDATE_PAPER1_TOTAL_MARKS,
)
from app.jee_main_exam_intelligence.contracts import PaperPlanSlot


def build_scoring_preview(slots: list[PaperPlanSlot]) -> dict[str, Any]:
    mcq = sum(1 for s in slots if (s.question_type or "mcq") == "mcq" or s.section_code)
    maximum = 0.0
    for slot in slots:
        marks = slot.marks if slot.marks is not None else CANDIDATE_MARKS_CORRECT
        maximum += marks
    return {
        "item_count": len(slots),
        "maximum_marks": maximum if slots else CANDIDATE_PAPER1_TOTAL_MARKS,
        "marking_scheme": {
            "correct": CANDIDATE_MARKS_CORRECT,
            "incorrect": CANDIDATE_MARKS_INCORRECT,
            "unattempted": CANDIDATE_MARKS_UNATTEMPTED,
        },
        "mcq_slot_count": mcq,
        "numerical_slot_count": len(slots) - mcq if slots else 0,
    }
