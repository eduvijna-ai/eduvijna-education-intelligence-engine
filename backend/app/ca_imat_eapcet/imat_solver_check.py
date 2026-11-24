from __future__ import annotations

from app.ca_imat_eapcet.constants import IMAT_OPTIONS_PER_QUESTION
from app.ca_imat_eapcet.content_validation import validate_and_bind_question_ref
from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict


def independent_imat_answer_check(
    question: QuestionRef,
) -> tuple[PlanVerdict, list[IssueCode], QuestionRef]:
    """D14-18: contained — no independent academic PASS."""

    from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED

    if ACADEMIC_VALIDATION_DISABLED:
        return (
            PlanVerdict.NOT_READY,
            [IssueCode.ACADEMIC_VALIDATION_CONTAINED],
            question.model_copy(update={"independently_validated": False}),
        )

    _, verdict, issues = validate_and_bind_question_ref(
        question,
        options_required=IMAT_OPTIONS_PER_QUESTION,
    )
    bound = question
    if verdict == PlanVerdict.PASS:
        bound = question.model_copy(update={"independently_validated": True})
    elif verdict == PlanVerdict.REVIEW_REQUIRED:
        bound = question.model_copy(update={"independently_validated": False})
    else:
        bound = question
    return verdict, issues, bound