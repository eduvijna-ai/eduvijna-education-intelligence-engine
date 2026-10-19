"""Day-7 diagnostic grounding checks for preflight (D9-08 / SC-R1/R2/R3)."""

from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import (
    MAX_DIAGNOSTIC_AGGREGATE_CHARS,
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.integration.day7_diagnostic_context import (
    measure_diagnostic_evidence_payload_chars,
)

_CITATION_LABEL = re.compile(r"^\[CIT-[^\]]+\]$", re.IGNORECASE)


def _canonical_sources(request: DiagnosticAuthoringRequest) -> list[str]:
    return [s for s in request.item.source_revision_ids if str(s).strip()]


def _visible_snippet_labels(request: DiagnosticAuthoringRequest) -> dict[str, str]:
    return {
        snippet.citation_label: snippet.source_revision_id
        for snippet in request.day7_evidence_snippets
        if (snippet.snippet or "").strip()
    }


def validate_diagnostic_grounding(request: DiagnosticAuthoringRequest) -> list[str]:
    issues: list[str] = []
    if measure_diagnostic_evidence_payload_chars(request) > MAX_DIAGNOSTIC_AGGREGATE_CHARS:
        issues.append("diagnostic_evidence_budget_exceeded")

    canonical_sources = _canonical_sources(request)
    allowed = [s for s in request.allowed_source_revision_ids if str(s).strip()]
    allowed_refs = {r for r in request.allowed_evidence_refs if str(r).strip()}
    canonical_set = set(canonical_sources)
    allowed_set = set(allowed)
    trusted = dict(request.trusted_citation_revision_map)

    if canonical_sources and not allowed:
        issues.append("source_authorization_unresolved")
        return issues

    if canonical_sources and not canonical_set.issubset(allowed_set):
        issues.append("unauthorized_source_revision")

    if canonical_sources and not trusted:
        nonempty_snippets = any(
            (snippet.snippet or "").strip() for snippet in request.day7_evidence_snippets
        )
        if nonempty_snippets:
            issues.append("untrusted_evidence_binding")

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
        if trusted:
            bound_revision = trusted.get(snippet.citation_label)
            if bound_revision is None or bound_revision != snippet.source_revision_id:
                issues.append("forged_evidence_ref")
                continue
        valid_snippets.append(snippet.citation_label)

    visible_by_label = _visible_snippet_labels(request)
    if canonical_sources and trusted:
        for label, bound_revision in trusted.items():
            visible_revision = visible_by_label.get(label)
            if visible_revision is None or visible_revision != bound_revision:
                issues.append("forged_evidence_ref")
    if canonical_sources:
        for label in allowed_refs:
            if not _CITATION_LABEL.match(label):
                continue
            if label in trusted:
                visible_revision = visible_by_label.get(label)
                if visible_revision is None or visible_revision != trusted[label]:
                    issues.append("forged_evidence_ref")
            elif label not in visible_by_label:
                issues.append("forged_evidence_ref")

    visible_revisions = {
        snippet.source_revision_id
        for snippet in request.day7_evidence_snippets
        if (snippet.snippet or "").strip()
    }
    if (
        canonical_sources
        and canonical_set - visible_revisions
        and valid_snippets
        and "unauthorized_source_revision" not in issues
    ):
        issues.append("insufficient_diagnostic_grounding")

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
