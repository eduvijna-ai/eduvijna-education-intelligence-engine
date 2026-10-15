from __future__ import annotations

from dataclasses import dataclass, field

from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest
from app.diagnostic_intelligence.eligibility import diagnostic_eligibility
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus


@dataclass(slots=True)
class DiagnosticPreflightResult:
    allow_model_call: bool
    status: DiagnosticValidationStatus
    issue_codes: list[str] = field(default_factory=list)
    candidate_codes: set[str] = field(default_factory=set)
    blocking: bool = False
    repairable: bool = False
    review_required: bool = False


def run_diagnostic_preflight(request: DiagnosticAuthoringRequest) -> DiagnosticPreflightResult:
    eligible, status, reason = diagnostic_eligibility(request.item)
    if not eligible:
        if status == DiagnosticValidationStatus.NOT_APPLICABLE:
            return DiagnosticPreflightResult(
                allow_model_call=False,
                status=status,
                issue_codes=[reason] if reason else [],
            )
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=status,
            issue_codes=[reason] if reason else [],
            blocking=status == DiagnosticValidationStatus.REJECT,
            repairable=status == DiagnosticValidationStatus.REPAIR,
            review_required=status == DiagnosticValidationStatus.REVIEW_REQUIRED,
        )

    if request.taxonomy_version.strip() == "":
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=DiagnosticValidationStatus.REJECT,
            issue_codes=["missing_taxonomy_version"],
            blocking=True,
        )

    candidates = resolve_misconception_candidates(request)
    codes = {c.misconception_code for c in candidates}
    if not codes:
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=DiagnosticValidationStatus.REVIEW_REQUIRED,
            issue_codes=["no_misconception_candidates"],
            review_required=True,
        )

    return DiagnosticPreflightResult(
        allow_model_call=True,
        status=DiagnosticValidationStatus.PASS,
        candidate_codes=codes,
    )
