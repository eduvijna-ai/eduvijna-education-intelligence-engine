from __future__ import annotations

from dataclasses import dataclass, field

from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest
from app.diagnostic_intelligence.eligibility import diagnostic_eligibility
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.diagnostic_intelligence.grounding import validate_diagnostic_grounding
from app.diagnostic_intelligence.scope_policy import validate_required_diagnostic_scope
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy


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

    try:
        load_taxonomy(request.taxonomy_version)
    except Exception:
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=DiagnosticValidationStatus.REJECT,
            issue_codes=["unknown_taxonomy_version"],
            blocking=True,
        )

    scope_issues = validate_required_diagnostic_scope(request)
    if scope_issues:
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=DiagnosticValidationStatus.REVIEW_REQUIRED,
            issue_codes=scope_issues,
            review_required=True,
        )

    grounding_issues = validate_diagnostic_grounding(request)
    if grounding_issues:
        blocking = any(
            code in {"unauthorized_source_revision", "source_authorization_unresolved"}
            for code in grounding_issues
        )
        return DiagnosticPreflightResult(
            allow_model_call=False,
            status=(
                DiagnosticValidationStatus.REJECT
                if blocking
                else DiagnosticValidationStatus.REVIEW_REQUIRED
            ),
            issue_codes=grounding_issues,
            blocking=blocking,
            review_required=not blocking,
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
