from __future__ import annotations

from app.adapters.anythingllm.types import AdapterRetrievalHit
from app.models.knowledge_intelligence import KnowledgeSourceBinding

_METADATA_ID_KEYS = (
    "docSource",
    "sourceDocument",
    "docId",
    "documentId",
    "document_id",
    "source_document_id",
)


def alternate_document_keys(binding: KnowledgeSourceBinding) -> tuple[str, ...]:
    keys: list[str] = []
    if binding.anythingllm_document_id:
        keys.append(binding.anythingllm_document_id)
    meta = binding.metadata_json
    for field in ("anythingllm_remote_location", "anythingllm_remote_doc_id"):
        value = meta.get(field)
        if isinstance(value, str) and value:
            keys.append(value)
    return tuple(dict.fromkeys(keys))


def build_binding_lookup(
    bindings: list[KnowledgeSourceBinding],
) -> dict[tuple[str, str], KnowledgeSourceBinding]:
    lookup: dict[tuple[str, str], KnowledgeSourceBinding] = {}
    for binding in bindings:
        workspace = binding.anythingllm_workspace
        for key in alternate_document_keys(binding):
            lookup[(workspace, key)] = binding
    return lookup


def match_binding_for_hit(
    hit: AdapterRetrievalHit,
    lookup: dict[tuple[str, str], KnowledgeSourceBinding],
) -> KnowledgeSourceBinding | None:
    direct = lookup.get((hit.workspace_slug, hit.document_id))
    if direct is not None:
        return direct
    metadata = hit.metadata or {}
    for key_name in _METADATA_ID_KEYS:
        candidate = metadata.get(key_name)
        if isinstance(candidate, str) and candidate:
            matched = lookup.get((hit.workspace_slug, candidate))
            if matched is not None:
                return matched
    return None
