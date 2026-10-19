"""Bounded Day-7 evidence for diagnostic generation (D9-08 / D9-13)."""

from __future__ import annotations

from app.diagnostic_intelligence.contracts import Day7DiagnosticEvidenceSnippet
from app.knowledge_intelligence.contracts import KnowledgeContextPack

MAX_DIAGNOSTIC_BOUNDED_CHARS = 4000


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


def build_diagnostic_day7_payload(
    context: KnowledgeContextPack,
    *,
    max_chars: int = MAX_DIAGNOSTIC_BOUNDED_CHARS,
) -> tuple[str, list[Day7DiagnosticEvidenceSnippet]]:
    snippets: list[Day7DiagnosticEvidenceSnippet] = []
    lines: list[str] = []
    used = 0
    for item in context.evidence:
        label = item.citation_label
        header = f"{label} (revision {item.source_revision_id}):"
        body = (item.snippet or "").strip()
        if not body:
            continue
        block = f"{header}\n{body}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining <= len(header) + 2:
                break
            body = body[: max(0, remaining - len(header) - 1)]
            block = f"{header}\n{body}"
        snippets.append(
            Day7DiagnosticEvidenceSnippet(
                citation_label=label,
                source_revision_id=item.source_revision_id,
                snippet=body,
            )
        )
        lines.append(block)
        used += len(block) + 7
        if used >= max_chars:
            break
    if context.bounded_text:
        bounded = context.bounded_text[:max_chars]
    else:
        bounded = "\n\n---\n\n".join(lines)
    if len(bounded) > max_chars:
        bounded = bounded[:max_chars]
    return bounded, snippets
