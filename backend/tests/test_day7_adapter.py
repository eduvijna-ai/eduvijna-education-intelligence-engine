from __future__ import annotations

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterError,
    AdapterRetrievalRequest,
    GatewayAvailability,
    IndexDocumentPayload,
    WorkspaceKey,
)

_STABLE_DOC_SOURCE = "eduvijna://knowledge/rev-1/ki-v1/" + "a" * 64


def test_fake_adapter_probe_and_deterministic_retrieval() -> None:
    adapter = FakeAnythingLLMAdapter()
    assert adapter.probe().availability == GatewayAvailability.AVAILABLE
    slug = adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    uploaded = adapter.upload_document(
        slug,
        IndexDocumentPayload(
            title="t",
            evidence_text="quadratic equations factorisation practice",
            content_checksum="abc",
            source_locator="loc",
            metadata={"docSource": _STABLE_DOC_SOURCE},
        ),
        idempotency_key="idem-1",
    )
    assert uploaded.stable_id == _STABLE_DOC_SOURCE
    hits = adapter.retrieve(
        AdapterRetrievalRequest(
            query_text="quadratic factorisation",
            top_k=3,
            workspace_slugs=(slug,),
        )
    )
    assert hits
    assert hits[0].rank == 1
    second = adapter.retrieve(
        AdapterRetrievalRequest(
            query_text="quadratic factorisation",
            top_k=3,
            workspace_slugs=(slug,),
        )
    )
    assert [item.document_id for item in hits] == [item.document_id for item in second]


def test_fake_adapter_idempotent_upload() -> None:
    adapter = FakeAnythingLLMAdapter()
    slug = adapter.ensure_workspace(WorkspaceKey(scope_key="global", slug="ws-global"))
    payload = IndexDocumentPayload(
        title="t",
        evidence_text="sample",
        content_checksum="abc",
        source_locator="loc",
        metadata={"docSource": _STABLE_DOC_SOURCE},
    )
    first = adapter.upload_document(slug, payload, idempotency_key="idem-2")
    second = adapter.upload_document(slug, payload, idempotency_key="idem-2")
    assert first.stable_id == second.stable_id


def test_fake_adapter_unavailable_simulation() -> None:
    adapter = FakeAnythingLLMAdapter(simulate_unauthorized=True)
    assert adapter.probe().availability == GatewayAvailability.UNAUTHORIZED
    try:
        adapter.ensure_workspace(WorkspaceKey(scope_key="x", slug="ws-x"))
    except AdapterError as exc:
        assert exc.code.value == "unauthorized"
    else:
        raise AssertionError("expected unauthorized")
