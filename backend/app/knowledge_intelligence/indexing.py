from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError
from app.knowledge_intelligence.audit import record_audit_event
from app.knowledge_intelligence.eligibility import assert_revision_index_eligible
from app.knowledge_intelligence.enums import KnowledgeAuditEventType, KnowledgeIndexStatus
from app.knowledge_intelligence.payload import build_index_payload
from app.knowledge_intelligence.retrieval_profile import (
    DEFAULT_RETRIEVAL_PROFILE_VERSION,
    load_retrieval_profile,
)
from app.knowledge_intelligence.scope import scope_from_source
from app.knowledge_intelligence.workspace import workspace_key_for_scope
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import Source, SourceRevision


class IndexingError(RuntimeError):
    pass


def _idempotency_key(revision: SourceRevision, profile_version: str) -> str:
    return f"{revision.id}:{revision.checksum}:{profile_version}"


def find_current_binding(
    session: Session,
    revision_id: str,
    profile_version: str,
) -> KnowledgeSourceBinding | None:
    return session.scalars(
        select(KnowledgeSourceBinding).where(
            KnowledgeSourceBinding.source_revision_id == revision_id,
            KnowledgeSourceBinding.retrieval_profile_version == profile_version,
        )
    ).first()


def find_active_binding_for_source(
    session: Session,
    source_id: str,
) -> KnowledgeSourceBinding | None:
    return session.scalars(
        select(KnowledgeSourceBinding)
        .where(
            KnowledgeSourceBinding.source_id == source_id,
            KnowledgeSourceBinding.index_status == KnowledgeIndexStatus.ACTIVE.value,
        )
        .order_by(KnowledgeSourceBinding.created_at.desc())
    ).first()


def list_active_bindings_for_source(
    session: Session,
    source_id: str,
) -> list[KnowledgeSourceBinding]:
    return list(
        session.scalars(
            select(KnowledgeSourceBinding)
            .where(
                KnowledgeSourceBinding.source_id == source_id,
                KnowledgeSourceBinding.index_status == KnowledgeIndexStatus.ACTIVE.value,
            )
            .order_by(
                KnowledgeSourceBinding.indexed_at.desc(),
                KnowledgeSourceBinding.created_at.desc(),
            )
        )
    )


def reconcile_supersession_for_source(
    session: Session,
    adapter: AnythingLLMAdapter,
    source_id: str,
    *,
    keep_binding_id: str,
    actor_id: str | None = None,
) -> list[str]:
    """Retry pending retirements and retire stale active bindings (D7-R06)."""
    actions: list[str] = []
    active_bindings = list_active_bindings_for_source(session, source_id)
    for binding in active_bindings:
        if binding.id == keep_binding_id:
            continue
        if binding.metadata_json.get("retire_retryable"):
            actions.append(f"retry_retire:{binding.id}")
        _retire_binding(
            session,
            adapter,
            binding,
            superseded_by=keep_binding_id,
            actor_id=actor_id,
        )
    return actions


def index_source_revision(
    session: Session,
    adapter: AnythingLLMAdapter,
    source_revision_id: str,
    *,
    retrieval_profile_version: str = DEFAULT_RETRIEVAL_PROFILE_VERSION,
    actor_id: str | None = None,
) -> KnowledgeSourceBinding:
    profile = load_retrieval_profile(retrieval_profile_version)
    revision = session.get(SourceRevision, source_revision_id)
    if revision is None:
        raise IndexingError(f"Unknown source revision: {source_revision_id}")
    source = session.get(Source, revision.source_id)
    if source is None:
        raise IndexingError(f"Unknown source for revision: {source_revision_id}")

    assert_revision_index_eligible(revision)

    existing = find_current_binding(session, revision.id, profile.version)
    if (
        existing is not None
        and existing.index_status == KnowledgeIndexStatus.ACTIVE.value
        and existing.source_revision_checksum == revision.checksum
    ):
        reconcile_supersession_for_source(
            session,
            adapter,
            source.id,
            keep_binding_id=existing.id,
            actor_id=actor_id,
        )
        return existing

    scope = scope_from_source(source)
    workspace_key = workspace_key_for_scope(scope)
    workspace_slug = adapter.ensure_workspace(workspace_key)
    payload = build_index_payload(source, revision)

    binding = existing or KnowledgeSourceBinding(
        source_id=source.id,
        source_revision_id=revision.id,
        source_revision_checksum=revision.checksum,
        anythingllm_workspace=workspace_slug,
        ownership_scope=scope.ownership_scope.value,
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        teacher_id=scope.teacher_id,
        index_status=KnowledgeIndexStatus.PENDING.value,
        retrieval_profile_version=profile.version,
        metadata_json={"workspace_scope_key": workspace_key.scope_key},
    )
    if existing is None:
        session.add(binding)
    binding.index_status = KnowledgeIndexStatus.INDEXING.value
    session.flush()

    record_audit_event(
        session,
        event_type=KnowledgeAuditEventType.INDEX_ATTEMPT,
        actor_id=actor_id,
        retrieval_profile_version=profile.version,
        workspaces_queried=[workspace_slug],
        source_revision_ids=[revision.id],
        payload={"binding_id": binding.id, "source_id": source.id},
    )

    try:
        uploaded = adapter.upload_document(
            workspace_slug,
            payload,
            idempotency_key=_idempotency_key(revision, profile.version),
        )
    except AdapterError as exc:
        binding.index_status = KnowledgeIndexStatus.FAILED.value
        binding.metadata_json = {
            **binding.metadata_json,
            "last_error": exc.message,
            "retryable": exc.retryable,
        }
        record_audit_event(
            session,
            event_type=KnowledgeAuditEventType.INDEX_FAILURE,
            actor_id=actor_id,
            retrieval_profile_version=profile.version,
            workspaces_queried=[workspace_slug],
            source_revision_ids=[revision.id],
            errors=[exc.message],
            payload={"binding_id": binding.id},
        )
        session.flush()
        raise IndexingError(exc.message) from exc

    prior_active = find_active_binding_for_source(session, source.id)
    binding.anythingllm_document_id = uploaded.stable_id
    binding.metadata_json = {
        **binding.metadata_json,
        "anythingllm_remote_doc_id": uploaded.remote_doc_id,
        "anythingllm_remote_location": uploaded.remote_location,
    }
    binding.index_status = KnowledgeIndexStatus.ACTIVE.value
    binding.indexed_at = datetime.now(UTC)
    binding.retired_at = None
    revision.anythingllm_document_id = uploaded.stable_id
    source.anythingllm_workspace = workspace_slug

    pending_remote_retire = False
    if prior_active is not None and prior_active.id != binding.id:
        _retire_binding(session, adapter, prior_active, superseded_by=binding.id, actor_id=actor_id)
        session.refresh(prior_active)
        pending_remote_retire = bool(prior_active.metadata_json.get("retire_retryable"))

    if not pending_remote_retire:
        reconcile_supersession_for_source(
            session,
            adapter,
            source.id,
            keep_binding_id=binding.id,
            actor_id=actor_id,
        )

    record_audit_event(
        session,
        event_type=KnowledgeAuditEventType.INDEX_SUCCESS,
        actor_id=actor_id,
        retrieval_profile_version=profile.version,
        workspaces_queried=[workspace_slug],
        source_revision_ids=[revision.id],
        payload={"binding_id": binding.id, "document_id": uploaded.stable_id},
    )
    session.flush()
    return binding


def _retire_binding(
    session: Session,
    adapter: AnythingLLMAdapter,
    binding: KnowledgeSourceBinding,
    *,
    superseded_by: str | None,
    actor_id: str | None,
) -> None:
    if binding.index_status in {
        KnowledgeIndexStatus.RETIRED.value,
        KnowledgeIndexStatus.SUPERSEDED.value,
    }:
        return
    if binding.anythingllm_document_id and binding.anythingllm_workspace:
        try:
            adapter.remove_document(binding.anythingllm_workspace, binding.anythingllm_document_id)
        except AdapterError as exc:
            binding.metadata_json = {
                **binding.metadata_json,
                "retire_error": exc.message,
                "retire_retryable": exc.retryable,
            }
            record_audit_event(
                session,
                event_type=KnowledgeAuditEventType.INDEX_RETIRE,
                actor_id=actor_id,
                retrieval_profile_version=binding.retrieval_profile_version,
                workspaces_queried=[binding.anythingllm_workspace],
                source_revision_ids=[binding.source_revision_id],
                warnings=[f"remote retire pending: {exc.message}"],
                payload={"binding_id": binding.id, "superseded_by": superseded_by},
            )
            session.flush()
            return
    if superseded_by:
        binding.index_status = KnowledgeIndexStatus.SUPERSEDED.value
    else:
        binding.index_status = KnowledgeIndexStatus.RETIRED.value
    binding.retired_at = datetime.now(UTC)
    binding.metadata_json = {
        **binding.metadata_json,
        "superseded_by": superseded_by,
        "retire_retryable": False,
    }
    record_audit_event(
        session,
        event_type=KnowledgeAuditEventType.INDEX_SUPERSEDE
        if superseded_by
        else KnowledgeAuditEventType.INDEX_RETIRE,
        actor_id=actor_id,
        retrieval_profile_version=binding.retrieval_profile_version,
        workspaces_queried=[binding.anythingllm_workspace],
        source_revision_ids=[binding.source_revision_id],
        payload={"binding_id": binding.id, "superseded_by": superseded_by},
    )
    session.flush()


def retire_binding(
    session: Session,
    adapter: AnythingLLMAdapter,
    binding_id: str,
    *,
    actor_id: str | None = None,
) -> KnowledgeSourceBinding:
    binding = session.get(KnowledgeSourceBinding, binding_id)
    if binding is None:
        raise IndexingError(f"Unknown binding: {binding_id}")
    _retire_binding(session, adapter, binding, superseded_by=None, actor_id=actor_id)
    return binding


def binding_snapshot(binding: KnowledgeSourceBinding) -> dict[str, Any]:
    return {
        "binding_id": binding.id,
        "source_id": binding.source_id,
        "source_revision_id": binding.source_revision_id,
        "source_revision_checksum": binding.source_revision_checksum,
        "anythingllm_workspace": binding.anythingllm_workspace,
        "anythingllm_document_id": binding.anythingllm_document_id,
        "ownership_scope": binding.ownership_scope,
        "index_status": binding.index_status,
        "indexed_at": binding.indexed_at.isoformat() if binding.indexed_at else None,
        "retired_at": binding.retired_at.isoformat() if binding.retired_at else None,
        "retrieval_profile_version": binding.retrieval_profile_version,
        "metadata_json": binding.metadata_json,
    }
