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


def trusted_citation_revision_map_from_pack(
    pack: KnowledgeContextPack,
) -> dict[str, str]:
    return {item.citation_label: item.source_revision_id for item in pack.evidence}


def measure_composed_evidence_chars(
    bounded_day7_context: str,
    snippets: list[Day7DiagnosticEvidenceSnippet],
) -> int:
    """Single aggregate budget formula shared by pack builder and request validator."""
    total = len(bounded_day7_context or "")
    for snippet in snippets:
        total += len(snippet.citation_label)
        total += len(snippet.source_revision_id)
        total += len(snippet.snippet or "")
        total += 16
    return total


def measure_diagnostic_evidence_payload_chars(request: DiagnosticAuthoringRequest) -> int:
    return measure_composed_evidence_chars(
        request.bounded_day7_context,
        request.day7_evidence_snippets,
    )


def _index_line(label: str, source_revision_id: str) -> str:
    return f"{label} (revision {source_revision_id})"


def build_diagnostic_day7_payload(
    context: KnowledgeContextPack,
    *,
    max_chars: int = MAX_DIAGNOSTIC_AGGREGATE_CHARS,
) -> tuple[str, list[Day7DiagnosticEvidenceSnippet]]:
    snippets: list[Day7DiagnosticEvidenceSnippet] = []
    index_lines: list[str] = []
    for item in context.evidence:
        label = item.citation_label
        body = (item.snippet or "").strip()
        if not body:
            continue
        index_line = _index_line(label, item.source_revision_id)
        included = False
        for body_len in range(min(len(body), MAX_DAY7_SNIPPET_CHARS), -1, -1):
            candidate_body = body[:body_len] if body_len else ""
            if not candidate_body:
                break
            candidate_snippet = Day7DiagnosticEvidenceSnippet(
                citation_label=label,
                source_revision_id=item.source_revision_id,
                snippet=candidate_body,
            )
            candidate_lines = index_lines + [index_line]
            candidate_bounded = "\n".join(candidate_lines)
            if len(candidate_bounded) > MAX_DIAGNOSTIC_BOUNDED_CHARS:
                continue
            candidate_snippets = snippets + [candidate_snippet]
            if measure_composed_evidence_chars(candidate_bounded, candidate_snippets) <= max_chars:
                snippets = candidate_snippets
                index_lines = candidate_lines
                included = True
                break
        if not included:
            continue
        if measure_composed_evidence_chars("\n".join(index_lines), snippets) >= max_chars:
            break
    bounded = "\n".join(index_lines)
    return bounded, snippets
