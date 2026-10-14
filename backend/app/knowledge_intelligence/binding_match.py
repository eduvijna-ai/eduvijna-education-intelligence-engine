from __future__ import annotations

from app.adapters.anythingllm.types import AdapterRetrievalHit
from app.models.knowledge_intelligence import KnowledgeSourceBinding

_DOC_SOURCE_METADATA_KEY = "anythingllm_doc_source_identity"


def persisted_doc_source_identity(binding: KnowledgeSourceBinding) -> str | None:
    value = binding.metadata_json.get(_DOC_SOURCE_METADATA_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def remote_removal_key(binding: KnowledgeSourceBinding) -> str | None:
    meta = binding.metadata_json
    for field in ("anythingllm_remote_location", "anythingllm_remote_doc_id"):
        value = meta.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if binding.anythingllm_document_id:
        return binding.anythingllm_document_id
    return None


def build_binding_lookup(
    bindings: list[KnowledgeSourceBinding],
) -> dict[tuple[str, str], KnowledgeSourceBinding]:
    lookup: dict[tuple[str, str], KnowledgeSourceBinding] = {}
    for binding in bindings:
        identity = persisted_doc_source_identity(binding)
        if identity is None:
            continue
        lookup[(binding.anythingllm_workspace, identity)] = binding
    return lookup


def match_binding_for_hit(
    hit: AdapterRetrievalHit,
    lookup: dict[tuple[str, str], KnowledgeSourceBinding],
) -> KnowledgeSourceBinding | None:
    metadata = hit.metadata or {}
    doc_source = metadata.get("docSource")
    if not isinstance(doc_source, str) or not doc_source.strip():
        return None
    if hit.document_id != doc_source:
        return None
    return lookup.get((hit.workspace_slug, doc_source))
