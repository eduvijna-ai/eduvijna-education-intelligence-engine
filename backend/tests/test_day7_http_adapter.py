from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterError,
    AdapterErrorCode,
    AdapterRetrievalRequest,
    IndexDocumentPayload,
    WorkspaceKey,
)


@dataclass
class _MockResponse:
    status_code: int
    _body: dict[str, Any] | list[Any]

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any] | list[Any]:
        return self._body


@pytest.fixture
def adapter() -> HttpAnythingLLMAdapter:
    return HttpAnythingLLMAdapter("http://anythingllm.test", "test-key")


_STABLE_DOC_SOURCE = "eduvijna://knowledge/rev-http/ki-v1/" + "c" * 64


def _payload(**extra: str) -> IndexDocumentPayload:
    return IndexDocumentPayload(
        title="t",
        evidence_text="evidence",
        content_checksum="abc",
        source_locator="loc",
        metadata={"docSource": _STABLE_DOC_SOURCE, **extra},
    )


def test_upload_parses_documents_array_and_adds_workspace(adapter: HttpAnythingLLMAdapter) -> None:
    captured: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        captured.append((method, path, {"json": json_body, "form": form_data, "files": files}))
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        return _MockResponse(
            200,
            {
                "success": True,
                "documents": [
                    {
                        "id": "doc-uuid-1",
                        "location": "custom-documents/doc-uuid-1.txt",
                        "docSource": _STABLE_DOC_SOURCE,
                    }
                ],
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    uploaded = adapter.upload_document(
        "ws-global",
        _payload(),
        idempotency_key="idem-http-1",
    )
    assert uploaded.stable_id == _STABLE_DOC_SOURCE
    assert uploaded.doc_source_identity == _STABLE_DOC_SOURCE
    assert uploaded.remote_doc_id == "doc-uuid-1"
    assert uploaded.remote_location == "custom-documents/doc-uuid-1.txt"
    upload_call = next(call for call in captured if call[1] == "/api/v1/document/upload")
    assert upload_call[0] == "POST"
    assert upload_call[2]["form"]["addToWorkspaces"] == "ws-global"
    metadata = json.loads(upload_call[2]["form"]["metadata"])
    assert metadata["docSource"] == _STABLE_DOC_SOURCE


def test_upload_doc_source_echo_mismatch_fails_closed(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        return _MockResponse(
            200,
            {
                "documents": [
                    {
                        "id": "doc-uuid-1",
                        "location": "custom-documents/doc-uuid-1.txt",
                        "docSource": "uploaded-file.txt",
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError) as exc:
        adapter.upload_document("ws-global", _payload(), idempotency_key="idem-mismatch")
    assert exc.value.code.value == "invalid_response"


def test_upload_doc_source_missing_echo_fails_closed(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        return _MockResponse(
            200,
            {
                "documents": [
                    {
                        "id": "doc-uuid-1",
                        "location": "custom-documents/doc-uuid-1.txt",
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError):
        adapter.upload_document("ws-global", _payload(), idempotency_key="idem-missing")


def test_ensure_workspace_resolves_existing_before_create(adapter: HttpAnythingLLMAdapter) -> None:
    calls: list[str] = []

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
        calls.append(path)
        if path == "/api/v1/workspaces":
            return _MockResponse(200, {"workspaces": [{"slug": "ws-global", "name": "ws-global"}]})
        raise AssertionError(f"unexpected path {path}")

    adapter._request = fake_request  # type: ignore[method-assign]
    slug = adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    assert slug == "ws-global"
    assert calls == ["/api/v1/workspaces"]


def test_two_uploads_same_workspace_do_not_require_create(adapter: HttpAnythingLLMAdapter) -> None:
    workspace_calls = 0

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        nonlocal workspace_calls
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        if path == "/api/v1/workspaces":
            workspace_calls += 1
            return _MockResponse(200, {"workspaces": [{"slug": "ws-global", "name": "ws-global"}]})
        if path == "/api/v1/document/upload":
            doc_id = f"doc-{workspace_calls}-{len(files or {})}"
            meta = json.loads((form_data or {})["metadata"])
            stable = meta["docSource"]
            return _MockResponse(
                200,
                {
                    "documents": [
                        {
                            "id": doc_id,
                            "location": f"custom-documents/{doc_id}.txt",
                            "docSource": stable,
                        },
                    ]
                },
            )
        raise AssertionError(path)

    adapter._request = fake_request  # type: ignore[method-assign]
    adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    for key in ("idem-a", "idem-b"):
        stable = f"eduvijna://knowledge/{key}/ki-v1/" + ("d" * 64)
        adapter.upload_document(
            "ws-global",
            IndexDocumentPayload(
                title="t",
                evidence_text="sample evidence text",
                content_checksum=key,
                source_locator="loc",
                metadata={"docSource": stable},
            ),
            idempotency_key=key,
        )
    assert workspace_calls == 2


def test_remove_uses_update_embeddings_deletes(adapter: HttpAnythingLLMAdapter) -> None:
    captured: list[tuple[str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
        captured.append((path, json_body))
        return _MockResponse(200, {"success": True})

    adapter._request = fake_request  # type: ignore[method-assign]
    adapter.remove_document("ws-global", "custom-documents/doc-1.txt")
    assert captured[0][0] == "/api/v1/workspace/ws-global/update-embeddings"
    assert captured[0][1] == {"deletes": ["custom-documents/doc-1.txt"]}


def test_vector_search_maps_chunk_to_doc_source(adapter: HttpAnythingLLMAdapter) -> None:
    stable = "eduvijna://knowledge/rev-1/ki-v1/" + "e" * 64
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
        return _MockResponse(
            200,
            {
                "results": [
                    {
                        "id": "chunk-uuid",
                        "text": "matched evidence",
                        "score": 0.91,
                        "metadata": {
                            "docSource": stable,
                            "chunkSource": "custom-documents/doc-1.txt#chunk-0",
                        },
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    response = adapter.retrieve(
        AdapterRetrievalRequest(
            query_text="evidence",
            top_k=3,
            workspace_slugs=("ws-global",),
        )
    )
    hits = response.hits
    assert hits[0].document_id == stable
    assert hits[0].metadata["docSource"] == stable
    assert hits[0].metadata["vector_chunk_id"] == "chunk-uuid"


def test_vector_search_skips_chunk_without_doc_source(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
        return _MockResponse(
            200,
            {
                "results": [
                    {
                        "id": "chunk-uuid-only",
                        "text": "orphan chunk",
                        "score": 0.5,
                        "metadata": {},
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    response = adapter.retrieve(
        AdapterRetrievalRequest(
            query_text="orphan",
            top_k=3,
            workspace_slugs=("ws-global",),
        )
    )
    assert response.hits == ()
    assert response.warnings == ("missing_doc_source:chunk-uuid-only",)


def test_upload_reuses_existing_doc_source_without_post(adapter: HttpAnythingLLMAdapter) -> None:
    upload_calls = 0

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        nonlocal upload_calls
        if path == "/api/v1/document/upload":
            upload_calls += 1
            raise AssertionError("upload should not be called when docSource already exists")
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(
                200,
                {
                    "workspace": [
                        {
                            "documents": [
                                {
                                    "id": "doc-existing",
                                    "location": "custom-documents/doc-existing.txt",
                                    "metadata": json.dumps({"docSource": _STABLE_DOC_SOURCE}),
                                }
                            ]
                        }
                    ]
                },
            )
        raise AssertionError(path)

    adapter._request = fake_request  # type: ignore[method-assign]
    uploaded = adapter.upload_document("ws-global", _payload(), idempotency_key="reuse")
    assert uploaded.remote_location == "custom-documents/doc-existing.txt"
    assert upload_calls == 0


def test_upload_timeout_reconciles_remote_document(adapter: HttpAnythingLLMAdapter) -> None:
    upload_calls = 0
    workspace_calls = 0

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        nonlocal upload_calls, workspace_calls
        if path == "/api/v1/document/upload":
            upload_calls += 1
            raise AdapterError(AdapterErrorCode.TIMEOUT, "timed out", retryable=True)
        if path == "/api/v1/workspace/ws-global":
            workspace_calls += 1
            if workspace_calls == 1:
                return _MockResponse(200, {"workspace": [{"documents": []}]})
            return _MockResponse(
                200,
                {
                    "workspace": [
                        {
                            "documents": [
                                {
                                    "id": "doc-late",
                                    "location": "custom-documents/doc-late.txt",
                                    "metadata": json.dumps({"docSource": _STABLE_DOC_SOURCE}),
                                }
                            ]
                        }
                    ]
                },
            )
        raise AssertionError(path)

    adapter._request = fake_request  # type: ignore[method-assign]
    uploaded = adapter.upload_document("ws-global", _payload(), idempotency_key="timeout-recover")
    assert uploaded.remote_location == "custom-documents/doc-late.txt"
    assert upload_calls == 1


def test_upload_timeout_without_reconciliation_fails(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        if path == "/api/v1/document/upload":
            raise AdapterError(AdapterErrorCode.TIMEOUT, "timed out", retryable=True)
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        raise AssertionError(path)

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError) as exc:
        adapter.upload_document("ws-global", _payload(), idempotency_key="timeout-fail")
    assert exc.value.code == AdapterErrorCode.AMBIGUOUS_UPLOAD


@dataclass
class _InvalidJsonResponse:
    status_code: int = 200

    @property
    def is_success(self) -> bool:
        return True

    def json(self) -> dict[str, Any]:
        raise ValueError("invalid json")


def test_workspace_array_response_lists_documents(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        return _MockResponse(
            200,
            {
                "workspace": [
                    {
                        "documents": [
                            {
                                "id": "doc-1",
                                "location": "custom-documents/doc-1.txt",
                                "metadata": json.dumps({"docSource": _STABLE_DOC_SOURCE}),
                            }
                        ]
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    docs = adapter._workspace_documents("ws-global")
    assert len(docs) == 1
    assert HttpAnythingLLMAdapter._extract_doc_source_from_document(docs[0]) == _STABLE_DOC_SOURCE


def test_malformed_workspace_response_raises(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        return _MockResponse(200, {"workspace": "not-an-array"})

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError) as exc:
        adapter._workspace_documents("ws-global")
    assert exc.value.code == AdapterErrorCode.INVALID_RESPONSE


def test_malformed_metadata_string_does_not_fabricate_doc_source() -> None:
    entry = {
        "id": "doc-x",
        "location": "custom-documents/doc-x.txt",
        "metadata": "{not-json",
    }
    assert HttpAnythingLLMAdapter._extract_doc_source_from_document(entry) is None


def test_invalid_json_maps_to_adapter_error(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _InvalidJsonResponse:
        return _InvalidJsonResponse()

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError) as exc:
        adapter.retrieve(
            AdapterRetrievalRequest(
                query_text="x",
                top_k=1,
                workspace_slugs=("ws-global",),
            )
        )
    assert exc.value.code == AdapterErrorCode.INVALID_RESPONSE


def test_malformed_upload_response_fails_closed(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        allow_retries: bool = True,
    ) -> _MockResponse:
        if path == "/api/v1/workspace/ws-global":
            return _MockResponse(200, {"documents": []})
        return _MockResponse(200, {"success": True})

    adapter._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(AdapterError):
        adapter.upload_document(
            "ws-global",
            IndexDocumentPayload(
                title="t",
                evidence_text="x",
                content_checksum="a",
                source_locator="loc",
                metadata={"docSource": _STABLE_DOC_SOURCE},
            ),
            idempotency_key="bad",
        )
