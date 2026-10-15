from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, MisconceptionStatus
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def _tag_scope_aligned(request_values: list[str], definition_values: list[str]) -> bool:
    if not request_values:
        return True
    if not definition_values:
        return True
    return bool(set(request_values).intersection(definition_values))


def validate_curriculum_scope(
    request: DiagnosticAuthoringRequest,
    tag: OptionDiagnosticTag,
    *,
    allowed_candidate_codes: set[str],
) -> list[str]:
    if tag.is_correct or not tag.misconception_code:
        return []
    if tag.misconception_code not in allowed_candidate_codes:
        return [DiagnosticIssueCode.NON_CANDIDATE_MISCONCEPTION.value]
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
    if not _tag_scope_aligned(request.topic_codes, definition.topic_codes):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    if not _tag_scope_aligned(request.concept_codes, definition.concept_codes):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    if not _tag_scope_aligned(request.competency_codes, definition.competency_codes):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    if not _tag_scope_aligned(
        request.learning_outcome_ids, definition.learning_outcome_ids
    ):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    return []
