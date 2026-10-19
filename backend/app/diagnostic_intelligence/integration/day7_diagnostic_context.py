"""Bounded Day-7 evidence for diagnostic generation (D9-08 / D9-13)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    MAX_DAY7_SNIPPET_CHARS,
    MAX_DIAGNOSTIC_AGGREGATE_CHARS,
    MAX_DIAGNOSTIC_BOUNDED_CHARS,
    Day7DiagnosticEvidenceSnippet,
    DiagnosticAuthoringRequest,
)
from app.knowledge_intelligence.contracts import KnowledgeContextPack


def filter_pack_for_item_sources(
    context: KnowledgeContextPack,
    *,
    item_source_revision_ids: list[str],
    blocked_revision_ids: set[str] | None = None,
) -> KnowledgeContextPack:
    """Keep only Day-7 evidence bound to this item's authorized source revisions."""
    authorized = set(item_source_revision_ids)
    blocked = blocked_revision_ids or set()
    evidence = [
        item
        for item in context.evidence
        if item.source_revision_id in authorized and item.source_revision_id not in blocked
    ]
    return context.model_copy(update={"evidence": evidence, "bounded_text": ""})


def measure_diagnostic_evidence_payload_chars(request: DiagnosticAuthoringRequest) -> int:
    total = len(request.bounded_day7_context or "")
    for snippet in request.day7_evidence_snippets:
        total += len(snippet.citation_label)
        total += len(snippet.source_revision_id)
        total += len(snippet.snippet or "")
        total += 16
    return total


def build_diagnostic_day7_payload(
    context: KnowledgeContextPack,
    *,
    max_chars: int = MAX_DIAGNOSTIC_AGGREGATE_CHARS,
) -> tuple[str, list[Day7DiagnosticEvidenceSnippet]]:
    snippets: list[Day7DiagnosticEvidenceSnippet] = []
    index_lines: list[str] = []
    content_used = 0
    for item in context.evidence:
        label = item.citation_label
        body = (item.snippet or "").strip()
        if not body:
            continue
        index_line = f"{label} (revision {item.source_revision_id})"
        line_cost = len(index_line) + 1
        remaining = max_chars - content_used - line_cost
        if remaining <= 0:
            break
        snippet_budget = min(MAX_DAY7_SNIPPET_CHARS, remaining)
        if len(body) > snippet_budget:
            body = body[:snippet_budget]
        snippets.append(
            Day7DiagnosticEvidenceSnippet(
                citation_label=label,
                source_revision_id=item.source_revision_id,
                snippet=body,
            )
        )
        index_lines.append(index_line)
        content_used += line_cost + len(body)
        if content_used >= max_chars:
            break
    bounded = "\n".join(index_lines)
    if len(bounded) > MAX_DIAGNOSTIC_BOUNDED_CHARS:
        bounded = bounded[:MAX_DIAGNOSTIC_BOUNDED_CHARS]
    return bounded, snippets
