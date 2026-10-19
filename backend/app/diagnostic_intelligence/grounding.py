"""Day-7 diagnostic grounding checks for preflight (D9-08 / SC-R1-02)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    MAX_DIAGNOSTIC_AGGREGATE_CHARS,
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.integration.day7_diagnostic_context import (
    aggregate_snippet_char_budget,
    diagnostic_grounding_present,
)


def validate_diagnostic_grounding(request: DiagnosticAuthoringRequest) -> list[str]:
    issues: list[str] = []
    canonical_sources = [s for s in request.item.source_revision_ids if str(s).strip()]
    if not canonical_sources:
        return issues

    allowed = [s for s in request.allowed_source_revision_ids if str(s).strip()]
    if not allowed:
        issues.append("source_authorization_unresolved")
        return issues

    canonical_set = set(canonical_sources)
    allowed_set = set(allowed)
    if not canonical_set.issubset(allowed_set):
        issues.append("unauthorized_source_revision")

    if not diagnostic_grounding_present(request):
        issues.append("insufficient_diagnostic_grounding")

    if aggregate_snippet_char_budget(request) > MAX_DIAGNOSTIC_AGGREGATE_CHARS:
        issues.append("diagnostic_evidence_budget_exceeded")
    if request.bounded_day7_context and len(request.bounded_day7_context) > 4000:
        issues.append("diagnostic_evidence_budget_exceeded")
    total_snippet = sum(len(s.snippet) for s in request.day7_evidence_snippets)
    if total_snippet > 4000:
        issues.append("diagnostic_evidence_budget_exceeded")

    return issues
