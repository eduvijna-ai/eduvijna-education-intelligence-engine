from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)


def test_diagnostic_audit_refs_persist() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            idempotency_key="day9-audit-persist",
        )
    )
    assert result.status == OrchestrationRunStatus.COMPLETED
    diag = (result.metadata_json.get("diagnostic_results") or [])[0]
    audit_ref = diag["audit_refs"][0]
    event = session.get(OrchestrationAuditEvent, audit_ref)
    assert event is not None
    assert event.node_name == "diagnostic_item"
    assert event.payload_json.get("diagnostic") is True
    assert event.payload_json.get("scope", {}).get("institution_id")
    session.close()


def test_diagnostic_audit_queryable_by_id() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ctx, service = build_day8_test_service(session)
    service.run(
        build_diagnostic_orchestration_request(ctx, idempotency_key="day9-audit-query")
    )
    session.commit()
    event = session.scalar(
        select(OrchestrationAuditEvent).where(
            OrchestrationAuditEvent.node_name == "diagnostic_item"
        )
    )
    assert event is not None
    assert "misconception_codes" in str(event.payload_json)
    session.close()
