from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterDocumentRef,
    AdapterError,
    AdapterErrorCode,
    AdapterRetrievalHit,
    AdapterRetrievalRequest,
    GatewayAvailability,
    GatewayProbeResult,
    IndexDocumentPayload,
    WorkspaceKey,
    availability_from_http_status,
)

logger = logging.getLogger("eduvijna.anythingllm")


class HttpAnythingLLMAdapter(AnythingLLMAdapter):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: AdapterError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.request(
                        method,
                        url,
                        headers=self._headers(),
                        json=json_body,
                        files=files,
                    )
            except httpx.TimeoutException:
                last_error = AdapterError(
                    AdapterErrorCode.TIMEOUT,
                    "AnythingLLM request timed out",
                    retryable=True,
                )
                if attempt < self._max_retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise last_error from None
            except httpx.HTTPError as exc:
                last_error = AdapterError(
                    AdapterErrorCode.UNAVAILABLE,
                    "AnythingLLM transport error",
                    retryable=True,
                )
                logger.debug("AnythingLLM transport failure: %s", type(exc).__name__)
                if attempt < self._max_retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise last_error from exc

            if response.status_code in {401, 403}:
                raise AdapterError(
                    AdapterErrorCode.UNAUTHORIZED,
                    "AnythingLLM unauthorized",
                    retryable=False,
                    http_status=response.status_code,
                )
            if response.status_code >= 500:
                last_error = AdapterError(
                    AdapterErrorCode.UNAVAILABLE,
                    f"AnythingLLM server error ({response.status_code})",
                    retryable=True,
                    http_status=response.status_code,
                )
                if attempt < self._max_retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise last_error
            if response.status_code >= 400:
                raise AdapterError(
                    AdapterErrorCode.HTTP_ERROR,
                    f"AnythingLLM client error ({response.status_code})",
                    retryable=False,
                    http_status=response.status_code,
                )
            return response
        if last_error is not None:
            raise last_error
        raise AdapterError(AdapterErrorCode.UNAVAILABLE, "AnythingLLM request failed")

    def probe(self) -> GatewayProbeResult:
        try:
            response = self._request("GET", "/api/ping")
        except AdapterError as exc:
            if exc.code == AdapterErrorCode.UNAUTHORIZED:
                return GatewayProbeResult(
                    availability=GatewayAvailability.UNAUTHORIZED,
                    message=exc.message,
                )
            return GatewayProbeResult(
                availability=GatewayAvailability.UNAVAILABLE,
                message=exc.message,
            )
        if not response.is_success:
            return GatewayProbeResult(
                availability=availability_from_http_status(response.status_code),
                message=f"ping status {response.status_code}",
            )
        return GatewayProbeResult(
            availability=GatewayAvailability.AVAILABLE,
            message="ping ok",
            capabilities=("workspace", "upload", "retrieve", "remove"),
        )

    def resolve_workspace(self, key: WorkspaceKey) -> str:
        return key.slug

    def ensure_workspace(self, key: WorkspaceKey) -> str:
        try:
            self._request(
                "POST",
                "/api/v1/workspace/new",
                json_body={"name": key.slug},
            )
        except AdapterError as exc:
            if exc.http_status != 409:
                raise
        return key.slug

    def upload_document(
        self,
        workspace_slug: str,
        payload: IndexDocumentPayload,
        *,
        idempotency_key: str,
    ) -> str:
        metadata = {
            **payload.metadata,
            "title": payload.title,
            "content_checksum": payload.content_checksum,
            "source_locator": payload.source_locator,
            "idempotency_key": idempotency_key,
            "evidence_role": "source_evidence",
        }
        files = {
            "file": (f"{idempotency_key}.txt", payload.evidence_text.encode("utf-8"), "text/plain"),
            "metadata": (None, str(metadata)),
        }
        response = self._request(
            "POST",
            f"/api/v1/document/upload/{workspace_slug}",
            files=files,
        )
        body = response.json()
        if not isinstance(body, dict):
            raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "upload response not object")
        document = body.get("document") or body
        if isinstance(document, dict):
            doc_id = document.get("id") or document.get("docId")
            if isinstance(doc_id, str) and doc_id:
                return doc_id
        raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "upload missing document id")

    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self._request(
            "DELETE",
            "/api/v1/document/remove-document",
            json_body={"workspaceSlug": workspace_slug, "documentId": document_id},
        )

    def lookup_document(
        self, workspace_slug: str, document_id: str
    ) -> AdapterDocumentRef | None:
        response = self._request("GET", f"/api/v1/workspace/{workspace_slug}")
        body = response.json()
        if not isinstance(body, dict):
            raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "workspace response not object")
        documents = body.get("documents") or body.get("workspace", {}).get("documents") or []
        if not isinstance(documents, list):
            return None
        for item in documents:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("id") or item.get("docId")
            if doc_id == document_id:
                title = item.get("title")
                return AdapterDocumentRef(
                    workspace_slug=workspace_slug,
                    document_id=document_id,
                    title=title if isinstance(title, str) else None,
                )
        return None

    def retrieve(self, request: AdapterRetrievalRequest) -> list[AdapterRetrievalHit]:
        hits: list[AdapterRetrievalHit] = []
        for workspace_slug in request.workspace_slugs:
            response = self._request(
                "POST",
                f"/api/v1/workspace/{workspace_slug}/vector-search",
                json_body={
                    "query": request.query_text,
                    "topN": request.top_k,
                    "scoreThreshold": 0.0,
                },
            )
            body = response.json()
            if not isinstance(body, dict):
                raise AdapterError(
                    AdapterErrorCode.INVALID_RESPONSE,
                    "vector-search response not object",
                )
            results = body.get("results") or body.get("documents") or []
            if not isinstance(results, list):
                raise AdapterError(
                    AdapterErrorCode.INVALID_RESPONSE,
                    "vector-search results not list",
                )
            for index, item in enumerate(results[: request.top_k]):
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or item.get("content") or ""
                doc_id = item.get("id") or item.get("docId") or item.get("documentId")
                if not isinstance(doc_id, str):
                    continue
                score_raw = item.get("score") or item.get("similarity") or 0.0
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.0
                metadata = item.get("metadata")
                hits.append(
                    AdapterRetrievalHit(
                        workspace_slug=workspace_slug,
                        document_id=doc_id,
                        text=str(text),
                        score=score,
                        rank=index + 1,
                        metadata=metadata if isinstance(metadata, dict) else {},
                    )
                )
        hits.sort(key=lambda h: (-h.score, h.workspace_slug, h.document_id))
        return hits[: request.top_k]
