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


def diagnostic_grounding_present(request: DiagnosticAuthoringRequest) -> bool:
    if request.day7_evidence_snippets:
        return True
    return bool(request.bounded_day7_context.strip())


def aggregate_snippet_char_budget(request: DiagnosticAuthoringRequest) -> int:
    bounded_len = len(request.bounded_day7_context or "")
    snippet_len = sum(len(s.snippet) for s in request.day7_evidence_snippets)
    return bounded_len + snippet_len


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
        if len(body) > MAX_DAY7_SNIPPET_CHARS:
            body = body[:MAX_DAY7_SNIPPET_CHARS]
        snippet_budget = min(
            MAX_DAY7_SNIPPET_CHARS,
            max_chars - content_used,
        )
        if snippet_budget <= 0:
            break
        if len(body) > snippet_budget:
            body = body[:snippet_budget]
        snippets.append(
            Day7DiagnosticEvidenceSnippet(
                citation_label=label,
                source_revision_id=item.source_revision_id,
                snippet=body,
            )
        )
        index_lines.append(f"{label} (revision {item.source_revision_id})")
        content_used += len(body)
        if content_used >= max_chars:
            break
    bounded = "\n".join(index_lines)
    if len(bounded) > MAX_DIAGNOSTIC_BOUNDED_CHARS:
        bounded = bounded[:MAX_DIAGNOSTIC_BOUNDED_CHARS]
    return bounded, snippets
