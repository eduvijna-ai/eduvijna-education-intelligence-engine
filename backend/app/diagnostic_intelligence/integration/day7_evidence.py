from __future__ import annotations

from app.knowledge_intelligence.contracts import KnowledgeContextPack


def bounded_evidence_from_context(
    context: KnowledgeContextPack,
) -> tuple[list[str], list[str]]:
    revision_ids = [item.source_revision_id for item in context.evidence]
    evidence_refs = [item.citation_label for item in context.evidence]
    return revision_ids, evidence_refs


def foreign_revision_ids(
    context: KnowledgeContextPack, candidate_revision_ids: set[str]
) -> set[str]:
    allowed = {item.source_revision_id for item in context.evidence}
    return candidate_revision_ids - allowed
