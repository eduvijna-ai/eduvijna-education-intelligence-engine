from __future__ import annotations

import json
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
    AdapterRetrievalResponse,
    AdapterUploadedDocument,
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

    @staticmethod
    def _json_body(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise AdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                "AnythingLLM response is not valid JSON",
                retryable=False,
                http_status=response.status_code,
            ) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: AdapterError | None = None
        attempts = (self._max_retries + 1) if allow_retries else 1
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.request(
                        method,
                        url,
                        headers=self._headers(),
                        json=json_body,
                        files=files,
                        data=form_data,
                    )
            except httpx.TimeoutException:
                last_error = AdapterError(
                    AdapterErrorCode.TIMEOUT,
                    "AnythingLLM request timed out",
                    retryable=True,
                )
                if allow_retries and attempt < attempts - 1:
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
                if allow_retries and attempt < attempts - 1:
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
                if allow_retries and attempt < attempts - 1:
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

    def _workspace_documents(self, workspace_slug: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/api/v1/workspace/{workspace_slug}")
        body = self._json_body(response)
        if not isinstance(body, dict):
            raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "workspace response not object")
        documents = body.get("documents") or body.get("workspace", {}).get("documents") or []
        if not isinstance(documents, list):
            return []
        return [item for item in documents if isinstance(item, dict)]

    def _find_workspace_slug(self, slug: str) -> str | None:
        response = self._request("GET", "/api/v1/workspaces")
        body = self._json_body(response)
        workspaces = body.get("workspaces") if isinstance(body, dict) else body
        if not isinstance(workspaces, list):
            return None
        for item in workspaces:
            if not isinstance(item, dict):
                continue
            candidate = item.get("slug") or item.get("name")
            if candidate == slug:
                return str(candidate)
        return None

    def resolve_workspace(self, key: WorkspaceKey) -> str:
        existing = self._find_workspace_slug(key.slug)
        return existing or key.slug

    def ensure_workspace(self, key: WorkspaceKey) -> str:
        existing = self._find_workspace_slug(key.slug)
        if existing:
            return existing
        try:
            self._request(
                "POST",
                "/api/v1/workspace/new",
                json_body={"name": key.slug},
            )
        except AdapterError as exc:
            if exc.http_status in {400, 409}:
                existing = self._find_workspace_slug(key.slug)
                if existing:
                    return existing
            raise
        return key.slug

    @staticmethod
    def _extract_doc_source_from_document(entry: dict[str, Any]) -> str | None:
        raw = entry.get("docSource")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        nested = entry.get("metadata")
        if isinstance(nested, dict):
            nested_source = nested.get("docSource")
            if isinstance(nested_source, str) and nested_source.strip():
                return nested_source.strip()
        return None

    @classmethod
    def _parse_uploaded_document(
        cls,
        body: dict[str, Any],
        *,
        expected_doc_source: str,
    ) -> AdapterUploadedDocument:
        documents = body.get("documents")
        if not isinstance(documents, list) or not documents:
            raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "upload missing documents[]")
        first = documents[0]
        if not isinstance(first, dict):
            raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "upload document entry invalid")
        returned_doc_source = cls._extract_doc_source_from_document(first)
        if returned_doc_source != expected_doc_source:
            raise AdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                "upload docSource echo missing or mismatched",
                retryable=True,
            )
        remote_doc_id = first.get("id") or first.get("docId")
        remote_location = first.get("location") or first.get("docpath") or first.get("path")
        if not isinstance(remote_location, str) or not remote_location.strip():
            raise AdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                "upload document missing remote location",
            )
        return AdapterUploadedDocument(
            stable_id=expected_doc_source,
            doc_source_identity=expected_doc_source,
            remote_doc_id=remote_doc_id if isinstance(remote_doc_id, str) else None,
            remote_location=remote_location.strip(),
        )

    def _reconcile_uploaded_document(
        self,
        workspace_slug: str,
        expected_doc_source: str,
    ) -> AdapterUploadedDocument | None:
        matches = [
            item
            for item in self._workspace_documents(workspace_slug)
            if self._extract_doc_source_from_document(item) == expected_doc_source
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise AdapterError(
                AdapterErrorCode.AMBIGUOUS_UPLOAD,
                "multiple remote documents share the same docSource",
                retryable=True,
            )
        return self._parse_uploaded_document(
            {"documents": matches},
            expected_doc_source=expected_doc_source,
        )

    def upload_document(
        self,
        workspace_slug: str,
        payload: IndexDocumentPayload,
        *,
        idempotency_key: str,
    ) -> AdapterUploadedDocument:
        expected_doc_source = payload.metadata.get("docSource")
        if not isinstance(expected_doc_source, str) or not expected_doc_source.strip():
            raise AdapterError(
                AdapterErrorCode.VALIDATION,
                "upload requires metadata.docSource stable identity",
                retryable=False,
            )
        expected_doc_source = expected_doc_source.strip()

        reconciled = self._reconcile_uploaded_document(workspace_slug, expected_doc_source)
        if reconciled is not None:
            return reconciled

        metadata = {
            **payload.metadata,
            "docSource": expected_doc_source,
            "title": payload.title,
            "content_checksum": payload.content_checksum,
            "source_locator": payload.source_locator,
            "idempotency_key": idempotency_key,
            "evidence_role": "source_evidence",
        }
        files = {
            "file": (
                f"{idempotency_key}.txt",
                payload.evidence_text.encode("utf-8"),
                "text/plain",
            ),
        }
        form_data = {
            "addToWorkspaces": workspace_slug,
            "metadata": json.dumps(metadata),
        }
        try:
            response = self._request(
                "POST",
                "/api/v1/document/upload",
                files=files,
                form_data=form_data,
                allow_retries=False,
            )
            body = self._json_body(response)
            if not isinstance(body, dict):
                raise AdapterError(AdapterErrorCode.INVALID_RESPONSE, "upload response not object")
            return self._parse_uploaded_document(body, expected_doc_source=expected_doc_source)
        except AdapterError as exc:
            if exc.code not in {
                AdapterErrorCode.TIMEOUT,
                AdapterErrorCode.UNAVAILABLE,
            }:
                raise
            recovered = self._reconcile_uploaded_document(workspace_slug, expected_doc_source)
            if recovered is not None:
                return recovered
            raise AdapterError(
                AdapterErrorCode.AMBIGUOUS_UPLOAD,
                "upload outcome ambiguous; remote document not provable",
                retryable=True,
            ) from exc

    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self._request(
            "POST",
            f"/api/v1/workspace/{workspace_slug}/update-embeddings",
            json_body={"deletes": [document_id]},
        )

    def lookup_document(
        self, workspace_slug: str, document_id: str
    ) -> AdapterDocumentRef | None:
        for item in self._workspace_documents(workspace_slug):
            doc_id = item.get("id") or item.get("docId")
            location = item.get("location") or item.get("docpath")
            if document_id in {doc_id, location}:
                title = item.get("title")
                return AdapterDocumentRef(
                    workspace_slug=workspace_slug,
                    document_id=str(doc_id or document_id),
                    title=title if isinstance(title, str) else None,
                )
        return None

    def retrieve(self, request: AdapterRetrievalRequest) -> AdapterRetrievalResponse:
        hits: list[AdapterRetrievalHit] = []
        warnings: list[str] = []
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
            body = self._json_body(response)
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
                raw_metadata = item.get("metadata")
                metadata: dict[str, Any] = {}
                if isinstance(raw_metadata, dict):
                    metadata = dict(raw_metadata)
                doc_source = metadata.get("docSource")
                chunk_id = item.get("id") or item.get("chunkId") or item.get("vectorId")
                chunk_label = chunk_id if isinstance(chunk_id, str) and chunk_id else "unknown"
                if not isinstance(doc_source, str) or not doc_source.strip():
                    warnings.append(f"missing_doc_source:{chunk_label}")
                    continue
                if isinstance(chunk_id, str):
                    metadata["vector_chunk_id"] = chunk_id
                hit_document_id = doc_source
                score_raw = item.get("score") or item.get("similarity") or 0.0
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.0
                hits.append(
                    AdapterRetrievalHit(
                        workspace_slug=workspace_slug,
                        document_id=hit_document_id,
                        text=str(text),
                        score=score,
                        rank=index + 1,
                        metadata=metadata,
                    )
                )
        hits.sort(key=lambda h: (-h.score, h.workspace_slug, h.document_id))
        limited = hits[: request.top_k]
        return AdapterRetrievalResponse(hits=tuple(limited), warnings=tuple(warnings))
