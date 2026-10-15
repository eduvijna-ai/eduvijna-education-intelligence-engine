from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.knowledge_intelligence.enums import KnowledgeAuditEventType
from app.models.knowledge_intelligence import KnowledgeAuditEvent


def new_query_id() -> str:
    return uuid.uuid4().hex


def hash_query_text(query_text: str) -> str:
    return hashlib.sha256(query_text.encode("utf-8")).hexdigest()


def record_audit_event(
    session: Session,
    *,
    event_type: KnowledgeAuditEventType,
    query_id: str | None = None,
    query_hash: str | None = None,
    organization_id: str | None = None,
    institution_id: str | None = None,
    teacher_id: str | None = None,
    actor_id: str | None = None,
    retrieval_profile_version: str | None = None,
    workspaces_queried: list[str] | None = None,
    source_revision_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> KnowledgeAuditEvent:
    event = KnowledgeAuditEvent(
        event_type=event_type.value,
        query_id=query_id,
        query_hash=query_hash,
        organization_id=organization_id,
        institution_id=institution_id,
        teacher_id=teacher_id,
        actor_id=actor_id,
        retrieval_profile_version=retrieval_profile_version,
        workspaces_queried_json=list(workspaces_queried or []),
        source_revision_ids_json=list(source_revision_ids or []),
        warnings_json=list(warnings or []),
        errors_json=list(errors or []),
        payload_json=dict(payload or {}),
    )
    session.add(event)
    session.flush()
    return event
