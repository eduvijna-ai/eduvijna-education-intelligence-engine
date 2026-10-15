from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, MisconceptionStatus
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def validate_curriculum_scope(
    request: DiagnosticAuthoringRequest, tag: OptionDiagnosticTag
) -> list[str]:
    if tag.is_correct or not tag.misconception_code:
        return []
    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=tag.taxonomy_version
    )
    if definition is None:
        return [DiagnosticIssueCode.UNKNOWN_MISCONCEPTION_CODE.value]
    if definition.status != MisconceptionStatus.ACTIVE:
        return [DiagnosticIssueCode.INACTIVE_MISCONCEPTION.value]
    if (
        request.subject_code
        and definition.subject_code
        and definition.subject_code != request.subject_code
    ):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    if request.grade_year_code and definition.grade_year_code:
        if definition.grade_year_code != request.grade_year_code:
            return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    if request.learning_outcome_ids and definition.learning_outcome_ids:
        if not set(request.learning_outcome_ids).intersection(definition.learning_outcome_ids):
            return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    return []
