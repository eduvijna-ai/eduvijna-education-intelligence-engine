from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.models.orchestration import OrchestrationAuditEvent
from app.prerequisite_intelligence.graph_verify import verify_production_graph_snapshot
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

    if execution_mode == TrustExecutionMode.PRODUCTION:
        run_id = (request.orchestration_run_id or "").strip()
        request_hash = (request.orchestration_request_hash or "").strip()
        if not run_id:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.orchestration_run_id")
        elif event.run_id != run_id:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_run_id")
        if not request_hash:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.orchestration_request_hash")
        elif event.request_hash != request_hash:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_request_hash")

        for scope_field in ("organization_id", "institution_id", "teacher_id"):
            req_val = getattr(request, scope_field, None)
            payload_val = payload.get(scope_field)
            if payload_val and req_val and str(payload_val) != str(req_val):
                issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
                paths.append(f"trusted_validation.day9_{scope_field}")
            if payload_val and not req_val:
                issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
                paths.append(f"trusted_validation.day9_{scope_field}")

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

    persisted_refs = list(option_trace.get("evidence_refs") or [])
    requested_refs = list(request.tag.evidence_refs or [])
    if persisted_refs or requested_refs:
        if sorted(persisted_refs) != sorted(requested_refs):
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_option_evidence_refs")

    raw_sources = event.source_revision_ids_json or {}
    if isinstance(raw_sources, dict):
        source_id_list = raw_sources.get("ids") or []
    else:
        source_id_list = raw_sources
    event_sources = {str(revision_id) for revision_id in source_id_list if revision_id}
    allowed = set(request.allowed_source_revision_ids or [])
    if execution_mode == TrustExecutionMode.PRODUCTION:
        if not allowed and event_sources:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_audit_sources")
        elif allowed and event_sources and not allowed.issubset(event_sources):
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_audit_sources")
        elif allowed and not event_sources:
            issues.append(RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION)
            paths.append("trusted_validation.day9_audit_sources")

    return issues, paths


def validate_graph_snapshot_attestation(
    request: RootCauseDiagnosticRequest,
    *,
    execution_mode: TrustExecutionMode,
    control_session: Session | None,
) -> tuple[list[RootCauseIssueCode], list[str], bool]:
    """Return issues, paths, and whether graph audit blocking applies."""
    return verify_production_graph_snapshot(
        control_session,
        request.graph_snapshot,
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        teacher_id=request.teacher_id,
        execution_mode=execution_mode,
    )
