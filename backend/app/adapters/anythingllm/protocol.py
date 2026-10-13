from __future__ import annotations

from typing import Protocol

from app.adapters.anythingllm.types import (
    AdapterDocumentRef,
    AdapterRetrievalHit,
    AdapterRetrievalRequest,
    AdapterUploadedDocument,
    GatewayProbeResult,
    IndexDocumentPayload,
    WorkspaceKey,
)


class AnythingLLMAdapter(Protocol):
    """Typed boundary for AnythingLLM — business code must not use HTTP directly."""

    def probe(self) -> GatewayProbeResult: ...

    def resolve_workspace(self, key: WorkspaceKey) -> str:
        """Return workspace slug for an existing or logical workspace key."""

    def ensure_workspace(self, key: WorkspaceKey) -> str:
        """Create workspace when policy allows; otherwise same as resolve."""

    def upload_document(
        self,
        workspace_slug: str,
        payload: IndexDocumentPayload,
        *,
        idempotency_key: str,
    ) -> AdapterUploadedDocument:
        """Upload/index document; returns stable remote identity for embed/remove."""

    def remove_document(self, workspace_slug: str, document_id: str) -> None: ...

    def lookup_document(
        self, workspace_slug: str, document_id: str
    ) -> AdapterDocumentRef | None: ...

    def retrieve(self, request: AdapterRetrievalRequest) -> list[AdapterRetrievalHit]: ...
