from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.platform_auth import SecurityAuditEvent


def record_security_event(
    session: Session,
    *,
    event_type: str,
    correlation_id: str,
    success: bool,
    organization_id: str | None = None,
    institution_id: str | None = None,
    principal_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    event = SecurityAuditEvent(
        id=uuid.uuid4().hex,
        event_type=event_type,
        organization_id=organization_id,
        institution_id=institution_id,
        principal_id=principal_id,
        correlation_id=correlation_id,
        success=success,
        metadata_json=metadata or {},
    )
    session.add(event)
    return event
