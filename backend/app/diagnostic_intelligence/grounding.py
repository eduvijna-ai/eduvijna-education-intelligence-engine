"""Day-7 diagnostic grounding checks for preflight (D9-08 / SC-R1/R2)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    MAX_DIAGNOSTIC_AGGREGATE_CHARS,
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.integration.day7_diagnostic_context import (
    measure_diagnostic_evidence_payload_chars,
)


def validate_diagnostic_grounding(request: DiagnosticAuthoringRequest) -> list[str]:
    issues: list[str] = []
    if measure_diagnostic_evidence_payload_chars(request) > MAX_DIAGNOSTIC_AGGREGATE_CHARS:
        issues.append("diagnostic_evidence_budget_exceeded")

    canonical_sources = [s for s in request.item.source_revision_ids if str(s).strip()]
    allowed = [s for s in request.allowed_source_revision_ids if str(s).strip()]
    allowed_refs = {r for r in request.allowed_evidence_refs if str(r).strip()}
    canonical_set = set(canonical_sources)
    allowed_set = set(allowed)

    if canonical_sources and not allowed:
        issues.append("source_authorization_unresolved")
        return issues

    if canonical_sources and not canonical_set.issubset(allowed_set):
        issues.append("unauthorized_source_revision")

    valid_snippets: list[str] = []
    for snippet in request.day7_evidence_snippets:
        body = (snippet.snippet or "").strip()
        if not body:
            continue
        if snippet.source_revision_id not in allowed_set:
            issues.append("unauthorized_source_revision")
            continue
        if canonical_sources and snippet.source_revision_id not in canonical_set:
            issues.append("unauthorized_source_revision")
            continue
        if snippet.citation_label not in allowed_refs:
            issues.append("forged_evidence_ref")
            continue
        valid_snippets.append(snippet.citation_label)

    bounded = (request.bounded_day7_context or "").strip()
    if canonical_sources:
        if not valid_snippets:
            issues.append("insufficient_diagnostic_grounding")
        elif bounded:
            if not any(label in bounded for label in valid_snippets):
                issues.append("insufficient_diagnostic_grounding")

    for snippet in request.day7_evidence_snippets:
        body = (snippet.snippet or "").strip()
        if not body:
            continue
        if bounded and snippet.citation_label not in bounded:
            issues.append("insufficient_diagnostic_grounding")

    return sorted(set(issues))
