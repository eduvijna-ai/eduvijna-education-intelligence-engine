from __future__ import annotations

from dataclasses import dataclass, field

from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode


@dataclass(slots=True)
class RootCausePreflightResult:
    allow_inference: bool
    blocking: bool
    issue_codes: list[RootCauseIssueCode] = field(default_factory=list)
    field_paths: list[str] = field(default_factory=list)


def run_root_cause_preflight(request: RootCauseDiagnosticRequest) -> RootCausePreflightResult:
    issues: list[RootCauseIssueCode] = []
    paths: list[str] = []

    if request.tag.is_correct:
        issues.append(RootCauseIssueCode.CORRECT_OPTION_TAGGED)
        paths.append("tag.is_correct")

    if request.day6_blocking:
        issues.append(RootCauseIssueCode.DAY6_BLOCKING)
        paths.append("day6_blocking")

    if request.tag.validation_status not in {
        DiagnosticValidationStatus.PASS,
        DiagnosticValidationStatus.REVIEW_REQUIRED,
    }:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.validation_status")

    if request.graph_snapshot is None or not request.graph_snapshot.nodes:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot")

    blocking = bool(issues)
    return RootCausePreflightResult(
        allow_inference=not blocking,
        blocking=blocking,
        issue_codes=issues,
        field_paths=paths,
    )
