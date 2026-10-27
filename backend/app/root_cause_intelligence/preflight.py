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

    if request.tag.validation_status != DiagnosticValidationStatus.PASS:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.validation_status")

    if request.item_id != request.tag.item_id:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.item_id")

    if request.option_key != request.tag.option_key:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.option_key")

    if request.misconception_code != (request.tag.misconception_code or ""):
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.misconception_code")

    if request.taxonomy_version != request.tag.taxonomy_version:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("tag.taxonomy_version")

    if request.curriculum_version_id != request.graph_snapshot.scope.curriculum_version_id:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("curriculum_version_id")

    if not request.graph_snapshot.nodes:
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.nodes")

    if not request.tag_validation_trusted:
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("tag_validation_trusted")

    blocking = bool(issues)
    return RootCausePreflightResult(
        allow_inference=not blocking,
        blocking=blocking,
        issue_codes=issues,
        field_paths=paths,
    )
