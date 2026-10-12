from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import GatewayProbeResult
from app.knowledge_intelligence.context_pack import build_context_pack
from app.knowledge_intelligence.contracts import (
    KnowledgeContextPack,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
)
from app.knowledge_intelligence.indexing import (
    binding_snapshot,
    index_source_revision,
    retire_binding,
)
from app.knowledge_intelligence.retrieval import retrieve_knowledge
from app.knowledge_intelligence.retrieval_profile import load_retrieval_profile
from app.models.knowledge_intelligence import KnowledgeSourceBinding


class KnowledgeIntelligenceService:
    """Framework-independent Knowledge Intelligence orchestration (D7-02)."""

    def __init__(
        self,
        session: Session,
        adapter: AnythingLLMAdapter | None = None,
    ) -> None:
        self._session = session
        self._adapter = adapter or build_anythingllm_adapter(force_fake=True)

    def probe_gateway(self) -> GatewayProbeResult:
        return self._adapter.probe()

    def index_source_revision(
        self,
        source_revision_id: str,
        *,
        retrieval_profile_version: str,
        actor_id: str | None = None,
    ) -> KnowledgeSourceBinding:
        return index_source_revision(
            self._session,
            self._adapter,
            source_revision_id,
            retrieval_profile_version=retrieval_profile_version,
            actor_id=actor_id,
        )

    def retire_binding(
        self, binding_id: str, *, actor_id: str | None = None
    ) -> KnowledgeSourceBinding:
        return retire_binding(self._session, self._adapter, binding_id, actor_id=actor_id)

    def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        return retrieve_knowledge(self._session, self._adapter, request)

    def build_context_pack(self, retrieval: KnowledgeRetrievalResult) -> KnowledgeContextPack:
        profile = load_retrieval_profile(retrieval.retrieval_profile_version)
        return build_context_pack(retrieval, profile)

    def inspect_binding(self, binding_id: str) -> dict[str, object]:
        binding = self._session.get(KnowledgeSourceBinding, binding_id)
        if binding is None:
            raise ValueError(f"Unknown binding: {binding_id}")
        return binding_snapshot(binding)
