from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterError,
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


def test_upload_parses_documents_array_and_adds_workspace(adapter: HttpAnythingLLMAdapter) -> None:
    captured: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
        captured.append((method, path, {"json": json_body, "form": form_data, "files": files}))
        return _MockResponse(
            200,
            {
                "success": True,
                "documents": [
                    {
                        "id": "doc-uuid-1",
                        "location": "custom-documents/doc-uuid-1.txt",
                    }
                ],
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    uploaded = adapter.upload_document(
        "ws-global",
        IndexDocumentPayload(
            title="t",
            evidence_text="evidence",
            content_checksum="abc",
            source_locator="loc",
        ),
        idempotency_key="idem-http-1",
    )
    assert uploaded.stable_id == "custom-documents/doc-uuid-1.txt"
    assert uploaded.remote_doc_id == "doc-uuid-1"
    assert captured[0][0] == "POST"
    assert captured[0][1] == "/api/v1/document/upload"
    assert json.loads(captured[0][2]["form"]["addToWorkspaces"]) == ["ws-global"]


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
    ) -> _MockResponse:
        nonlocal workspace_calls
        if path == "/api/v1/workspaces":
            workspace_calls += 1
            return _MockResponse(200, {"workspaces": [{"slug": "ws-global", "name": "ws-global"}]})
        if path == "/api/v1/document/upload":
            doc_id = f"doc-{workspace_calls}-{len(files or {})}"
            return _MockResponse(
                200,
                {
                    "documents": [
                        {"id": doc_id, "location": f"custom-documents/{doc_id}.txt"},
                    ]
                },
            )
        raise AssertionError(path)

    adapter._request = fake_request  # type: ignore[method-assign]
    adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    for key in ("idem-a", "idem-b"):
        adapter.upload_document(
            "ws-global",
            IndexDocumentPayload(
                title="t",
                evidence_text="sample evidence text",
                content_checksum=key,
                source_locator="loc",
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


def test_vector_search_maps_chunk_to_source_document(adapter: HttpAnythingLLMAdapter) -> None:
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
                        "id": "vector-chunk-9",
                        "text": "matched evidence",
                        "score": 0.91,
                        "metadata": {"sourceDocument": "custom-documents/doc-1.txt"},
                    }
                ]
            },
        )

    adapter._request = fake_request  # type: ignore[method-assign]
    hits = adapter.retrieve(
        AdapterRetrievalRequest(
            query_text="evidence",
            top_k=3,
            workspace_slugs=("ws-global",),
        )
    )
    assert hits[0].document_id == "vector-chunk-9"
    assert hits[0].metadata["sourceDocument"] == "custom-documents/doc-1.txt"


def test_malformed_upload_response_fails_closed(adapter: HttpAnythingLLMAdapter) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> _MockResponse:
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
            ),
            idempotency_key="bad",
        )
