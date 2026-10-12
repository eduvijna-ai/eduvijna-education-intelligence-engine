from __future__ import annotations

from app.knowledge_intelligence.contracts import (
    KnowledgeContextPack,
    KnowledgeEvidenceItem,
    KnowledgeRetrievalResult,
)
from app.knowledge_intelligence.retrieval_profile import RetrievalProfile


def format_citation(item: KnowledgeEvidenceItem) -> str:
    return (
        f"[{item.citation_label}] {item.title} "
        f"(rev={item.source_revision_id[:8]}, tier={item.trust_tier})"
    )


def build_context_pack(
    retrieval: KnowledgeRetrievalResult,
    profile: RetrievalProfile,
) -> KnowledgeContextPack:
    warnings = list(retrieval.warnings)
    retained: list[KnowledgeEvidenceItem] = []
    char_budget = profile.max_context_characters
    used_chars = 0
    truncated_items = 0

    for item in retrieval.items:
        if len(retained) >= profile.max_context_items:
            truncated_items += 1
            continue
        snippet = item.snippet
        if used_chars + len(snippet) > char_budget:
            remaining = max(char_budget - used_chars, 0)
            if remaining <= 0:
                truncated_items += 1
                continue
            snippet = snippet[:remaining]
            warnings.append("context_truncated_snippet")
        used_chars += len(snippet)
        retained.append(item.model_copy(update={"snippet": snippet}))

    if truncated_items:
        warnings.append(f"context_overflow_dropped_items:{truncated_items}")

    citations = [format_citation(item) for item in retained]
    bounded_lines = [
        f"{citation}\n{item.snippet}"
        for citation, item in zip(citations, retained, strict=True)
    ]
    bounded_text = "\n\n---\n\n".join(bounded_lines)

    return KnowledgeContextPack(
        query_text=retrieval.query_text,
        retrieval_profile_version=retrieval.retrieval_profile_version,
        query_id=retrieval.query_id,
        evidence=retained,
        citations=citations,
        scope=retrieval.scope_applied,
        warnings=warnings,
        bounded_text=bounded_text,
        truncated_item_count=truncated_items,
        truncated_character_count=max(0, sum(len(i.snippet) for i in retrieval.items) - used_chars),
    )
