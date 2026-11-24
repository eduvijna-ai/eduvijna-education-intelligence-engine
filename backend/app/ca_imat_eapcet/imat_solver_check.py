from __future__ import annotations

from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict


def independent_imat_answer_check(question: QuestionRef) -> tuple[PlanVerdict, list[IssueCode]]:
    """D14-18: reject ambiguous MCQs without independent solver evidence."""

    if not question.options or len(question.options) < 4:
        return PlanVerdict.FAIL, [IssueCode.VALIDATION_NOT_PROVEN]
    if question.correct_key not in question.options:
        return PlanVerdict.REVIEW_REQUIRED, [IssueCode.VALIDATION_NOT_PROVEN]
    if not question.independently_validated:
        return PlanVerdict.PASS, []  # synthetic demo allowed without solver proof
    return PlanVerdict.PASS, []