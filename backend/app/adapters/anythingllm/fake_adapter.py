from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterDocumentRef,
    AdapterError,
    AdapterErrorCode,
    AdapterRetrievalHit,
    AdapterRetrievalRequest,
    AdapterUploadedDocument,
    GatewayAvailability,
    GatewayProbeResult,
    IndexDocumentPayload,
    WorkspaceKey,
)


@dataclass
class _StoredDocument:
    workspace_slug: str
    document_id: str
    title: str
    evidence_text: str
    content_checksum: str
    source_locator: str
    metadata: dict[str, object] = field(default_factory=dict)
    idempotency_key: str | None = None


class FakeAnythingLLMAdapter(AnythingLLMAdapter):
    """Deterministic in-memory AnythingLLM double for CI and unit tests."""

    def __init__(
        self,
        *,
        simulate_unavailable: bool = False,
        simulate_unauthorized: bool = False,
        simulate_timeout: bool = False,
        simulate_invalid_response: bool = False,
    ) -> None:
        self._simulate_unavailable = simulate_unavailable
        self._simulate_unauthorized = simulate_unauthorized
        self._simulate_timeout = simulate_timeout
        self._simulate_invalid_response = simulate_invalid_response
        self._workspaces: set[str] = set()
        self._documents: dict[tuple[str, str], _StoredDocument] = {}
        self._idempotency: dict[str, str] = {}

    def probe(self) -> GatewayProbeResult:
        if self._simulate_timeout:
            return GatewayProbeResult(
                availability=GatewayAvailability.UNAVAILABLE,
                message="simulated timeout",
            )
        if self._simulate_unauthorized:
            return GatewayProbeResult(
                availability=GatewayAvailability.UNAUTHORIZED,
                message="simulated unauthorized",
            )
        if self._simulate_unavailable:
            return GatewayProbeResult(
                availability=GatewayAvailability.UNAVAILABLE,
                message="simulated unavailable",
            )
        if self._simulate_invalid_response:
            return GatewayProbeResult(
                availability=GatewayAvailability.INVALID_RESPONSE,
                message="simulated invalid response",
            )
        return GatewayProbeResult(
            availability=GatewayAvailability.AVAILABLE,
            message="fake adapter ready",
            capabilities=("workspace", "upload", "retrieve", "remove"),
        )

    def _guard(self) -> None:
        if self._simulate_timeout:
            raise AdapterError(AdapterErrorCode.TIMEOUT, "simulated timeout", retryable=True)
        if self._simulate_unauthorized:
            raise AdapterError(
                AdapterErrorCode.UNAUTHORIZED,
                "simulated unauthorized",
                retryable=False,
                http_status=401,
            )
        if self._simulate_unavailable:
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE,
                "simulated unavailable",
                retryable=True,
                http_status=503,
            )
        if self._simulate_invalid_response:
            raise AdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                "simulated invalid response",
                retryable=False,
            )

    def resolve_workspace(self, key: WorkspaceKey) -> str:
        self._guard()
        self._workspaces.add(key.slug)
        return key.slug

    def ensure_workspace(self, key: WorkspaceKey) -> str:
        return self.resolve_workspace(key)

    def upload_document(
        self,
        workspace_slug: str,
        payload: IndexDocumentPayload,
        *,
        idempotency_key: str,
    ) -> AdapterUploadedDocument:
        self._guard()
        if idempotency_key in self._idempotency:
            existing_id = self._idempotency[idempotency_key]
            doc = self._documents.get((workspace_slug, existing_id))
            if doc is not None:
                location = f"custom-documents/{existing_id}.txt"
                return AdapterUploadedDocument(
                    stable_id=location,
                    remote_doc_id=existing_id,
                    remote_location=location,
                )
        document_id = hashlib.sha256(
            f"{workspace_slug}:{payload.content_checksum}:{idempotency_key}".encode()
        ).hexdigest()[:24]
        location = f"custom-documents/{document_id}.txt"
        self._workspaces.add(workspace_slug)
        self._documents[(workspace_slug, document_id)] = _StoredDocument(
            workspace_slug=workspace_slug,
            document_id=document_id,
            title=payload.title,
            evidence_text=payload.evidence_text,
            content_checksum=payload.content_checksum,
            source_locator=payload.source_locator,
            metadata=dict(payload.metadata),
            idempotency_key=idempotency_key,
        )
        self._idempotency[idempotency_key] = document_id
        return AdapterUploadedDocument(
            stable_id=location,
            remote_doc_id=document_id,
            remote_location=location,
        )

    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self._guard()
        if (workspace_slug, document_id) in self._documents:
            self._documents.pop((workspace_slug, document_id), None)
            return
        for key in list(self._documents):
            ws, internal_id = key
            if ws != workspace_slug:
                continue
            location = f"custom-documents/{internal_id}.txt"
            if document_id in {internal_id, location}:
                self._documents.pop(key, None)
                return

    def lookup_document(
        self, workspace_slug: str, document_id: str
    ) -> AdapterDocumentRef | None:
        self._guard()
        doc = self._documents.get((workspace_slug, document_id))
        if doc is None:
            return None
        return AdapterDocumentRef(
            workspace_slug=workspace_slug,
            document_id=document_id,
            title=doc.title,
        )

    def retrieve(self, request: AdapterRetrievalRequest) -> list[AdapterRetrievalHit]:
        self._guard()
        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", request.query_text.lower())
            if len(token) > 2
        }
        hits: list[AdapterRetrievalHit] = []
        for workspace_slug in request.workspace_slugs:
            for (ws, _), doc in sorted(
                self._documents.items(), key=lambda item: (item[0][0], item[0][1])
            ):
                if ws != workspace_slug:
                    continue
                if request.metadata_filters:
                    meta = doc.metadata
                    if not all(meta.get(k) == v for k, v in request.metadata_filters.items()):
                        continue
                doc_tokens = set(re.findall(r"[a-z0-9]+", doc.evidence_text.lower()))
                overlap = len(query_tokens & doc_tokens)
                score = float(overlap) / float(max(len(query_tokens), 1))
                if score <= 0 and query_tokens:
                    continue
                if not query_tokens:
                    score = 0.1
                chunk_id = f"chunk-{doc.document_id}"
                hits.append(
                    AdapterRetrievalHit(
                        workspace_slug=workspace_slug,
                        document_id=chunk_id,
                        text=doc.evidence_text,
                        score=score,
                        rank=0,
                        metadata={
                            **dict(doc.metadata),
                            "sourceDocument": doc.document_id,
                            "docId": doc.document_id,
                        },
                    )
                )
        hits.sort(key=lambda h: (-h.score, h.workspace_slug, h.document_id))
        limited = hits[: request.top_k]
        return [
            AdapterRetrievalHit(
                workspace_slug=item.workspace_slug,
                document_id=item.document_id,
                text=item.text,
                score=item.score,
                rank=index + 1,
                metadata=item.metadata,
            )
            for index, item in enumerate(limited)
        ]
