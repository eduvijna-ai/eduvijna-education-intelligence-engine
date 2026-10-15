from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationAuditEvent


def persist_audit_event(
    session: Session,
    *,
    run_id: str,
    request_hash: str,
    node_name: str,
    status: str,
    attempt: int = 1,
    prompt_version: str | None = None,
    source_revision_ids: list[str] | None = None,
    issue_codes: list[str] | None = None,
    gateway_request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> OrchestrationAuditEvent:
    event = OrchestrationAuditEvent(
        run_id=run_id,
        request_hash=request_hash,
        node_name=node_name,
        status=status,
        attempt=attempt,
        prompt_version=prompt_version,
        source_revision_ids_json={"ids": source_revision_ids or []},
        issue_codes_json=issue_codes or [],
        gateway_request_id=gateway_request_id,
        payload_json=payload or {},
    )
    session.add(event)
    session.flush()
    assert event.id is not None
    return event
