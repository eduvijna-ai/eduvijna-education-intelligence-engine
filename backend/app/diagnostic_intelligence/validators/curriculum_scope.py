from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, MisconceptionStatus
from app.diagnostic_intelligence.scope_policy import definition_matches_request_scope
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


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
    if not definition_matches_request_scope(request, definition):
        return [DiagnosticIssueCode.CURRICULUM_SCOPE_MISMATCH.value]
    return []
