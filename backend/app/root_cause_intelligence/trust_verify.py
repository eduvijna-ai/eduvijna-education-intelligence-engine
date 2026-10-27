from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.models.orchestration import OrchestrationAuditEvent
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode
from app.root_cause_intelligence.trusted_validation import (
    RootCauseTrustedValidationContext,
    synthetic_harness_allowed,
    trusted_context_matches_request,
)

_ACCEPTED_DIAGNOSTIC_STATUSES = {"pass", "accepted", "ok"}


def verify_root_cause_trusted_context(
    trusted: RootCauseTrustedValidationContext,
    request: RootCauseDiagnosticRequest,
    *,
    execution_mode: TrustExecutionMode,
    control_session: Session | None,
) -> tuple[list[RootCauseIssueCode], list[str]]:
    issues: list[RootCauseIssueCode] = []
    paths: list[str] = []

    if not trusted_context_matches_request(
        request.item_id,
        request.option_key,
        request.misconception_code,
        request.taxonomy_version,
        trusted,
    ):
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.identity")
        return issues, paths

    if trusted.trust_source == "synthetic_fixture_harness":
        if execution_mode != TrustExecutionMode.SYNTHETIC_FIXTURE:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.synthetic_harness_forbidden")
        elif not synthetic_harness_allowed(request.graph_snapshot):
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.synthetic_harness")
        return issues, paths

    if control_session is None:
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.missing_control_session")
        return issues, paths

    if not trusted.day9_audit_ref:
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.day9_audit_ref")
        return issues, paths

    event = control_session.get(OrchestrationAuditEvent, trusted.day9_audit_ref)
    if event is None or event.node_name != "diagnostic_item":
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.day9_audit_event")
        return issues, paths

    if str(event.status).lower() not in _ACCEPTED_DIAGNOSTIC_STATUSES:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("trusted_validation.day9_audit_status")

    payload = event.payload_json or {}
    if str(payload.get("item_id")) != request.item_id:
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.day9_audit_item")

    traces = payload.get("option_traces") or []
    option_trace = next(
        (
            trace
            for trace in traces
            if trace.get("option_key") == request.option_key and not trace.get("item_level")
        ),
        None,
    )
    if option_trace is None:
        issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
        paths.append("trusted_validation.day9_option_trace")
        return issues, paths

    trace_status = str(option_trace.get("validation_status") or "").lower()
    if trace_status != DiagnosticValidationStatus.PASS.value:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("trusted_validation.day9_option_status")

    if str(option_trace.get("misconception_code") or "") != request.misconception_code:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("trusted_validation.day9_option_misconception")

    audit_taxonomy = str(payload.get("taxonomy_version") or "")
    if audit_taxonomy and audit_taxonomy != request.taxonomy_version:
        issues.append(RootCauseIssueCode.DAY9_TAG_REJECTED)
        paths.append("trusted_validation.day9_taxonomy")

    return issues, paths


def validate_graph_snapshot_attestation(
    request: RootCauseDiagnosticRequest,
) -> tuple[list[RootCauseIssueCode], list[str], bool]:
    """Return issues, paths, and whether graph audit blocking applies."""
    issues: list[RootCauseIssueCode] = []
    paths: list[str] = []
    meta = request.graph_snapshot.metadata_json or {}
    if not meta.get("loader_attested"):
        issues.append(RootCauseIssueCode.MISSING_GRAPH)
        paths.append("graph_snapshot.loader_attested")
        return issues, paths, True

    loader_scope = meta.get("loader_scope") or {}
    scope = request.graph_snapshot.scope

    def _mismatch(field: str, request_value: str | None, loader_value: str | None) -> None:
        if request_value and loader_value and request_value != loader_value:
            issues.append(RootCauseIssueCode.FOREIGN_TENANT)
            paths.append(f"graph_snapshot.scope.{field}")

    _mismatch("organization_id", request.organization_id, loader_scope.get("organization_id"))
    _mismatch("institution_id", request.institution_id, loader_scope.get("institution_id"))
    _mismatch("teacher_id", request.teacher_id, loader_scope.get("teacher_id"))
    _mismatch("medium_code", scope.medium_code, loader_scope.get("medium_code"))
    _mismatch("subject_code", scope.subject_code, loader_scope.get("subject_code"))
    _mismatch("grade_year_code", scope.grade_year_code, loader_scope.get("grade_year_code"))

    blocking = bool(issues)
    return issues, paths, blocking
