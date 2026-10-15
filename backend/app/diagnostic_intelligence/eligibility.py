from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticQuestionItem
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus

_SUPPORTED_TYPES = frozenset({"single_choice", "mcq", "multiple_choice_single"})


def diagnostic_eligibility(
    item: DiagnosticQuestionItem,
) -> tuple[bool, DiagnosticValidationStatus, str]:
    if item.question_type not in _SUPPORTED_TYPES:
        return False, DiagnosticValidationStatus.NOT_APPLICABLE, "unsupported_question_type"
    if len(item.options) < 2:
        return False, DiagnosticValidationStatus.REVIEW_REQUIRED, "insufficient_options"
    correct = [o for o in item.options if o.is_correct]
    if len(correct) != 1:
        return False, DiagnosticValidationStatus.REJECT, "correct_cardinality_invalid"
    return True, DiagnosticValidationStatus.PASS, "eligible"
