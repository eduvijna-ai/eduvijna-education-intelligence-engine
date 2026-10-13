from __future__ import annotations

from app.adapters.anythingllm.types import IndexDocumentPayload
from app.knowledge_intelligence.scope import authority_label_for_source
from app.models.source import Source, SourceRevision


def build_index_payload(source: Source, revision: SourceRevision) -> IndexDocumentPayload:
    evidence_text = revision.extracted_text or ""
    title = source.title
    locator = source.url or f"source:{source.id}/revision:{revision.id}"
    return IndexDocumentPayload(
        title=title,
        evidence_text=evidence_text,
        content_checksum=revision.checksum,
        source_locator=locator,
        metadata={
            "source_id": source.id,
            "source_revision_id": revision.id,
            "source_revision_checksum": revision.checksum,
            "trust_tier": source.trust_tier,
            "authority_label": authority_label_for_source(source),
            "source_type": source.source_type,
            "evidence_role": "source_evidence",
            "instruction_boundary": "untrusted_evidence_only",
        },
    )
