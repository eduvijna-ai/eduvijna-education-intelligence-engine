from __future__ import annotations

from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.orchestration.contracts import DraftQuestionItem, ResolvedScope


def day6_blocking_for_item(
    education_service: EducationIntelligenceValidationService,
    item: DraftQuestionItem,
    scope: ResolvedScope,
    *,
    request_marks: float | None,
) -> list[str]:
    from app.orchestration.canonical_mapping import draft_to_canonical

    canonical = draft_to_canonical(item, scope, request_marks=request_marks)
    summary = education_service.validate_item(
        canonical,
        curriculum_version_id=scope.curriculum_version_id,
        persist=False,
    )
    if summary.blocking_failure or summary.aggregate_status == ValidationStatus.FAIL:
        return [DiagnosticIssueCode.DAY6_BLOCKING.value]
    return []
