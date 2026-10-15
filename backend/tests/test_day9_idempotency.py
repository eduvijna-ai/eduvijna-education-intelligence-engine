from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)


def test_diagnostic_idempotent_replay() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ctx, service = build_day8_test_service(session)
    request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-idem-key-12345",
    )
    first = service.run(request)
    second = service.run(request)
    assert first.run_id == second.run_id
    session.close()


def test_diagnostic_idempotency_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ctx, service = build_day8_test_service(session)
    base = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-conflict-key-99",
    )
    service.run(base)
    conflict = build_diagnostic_orchestration_request(
        ctx,
        diagnostic_scenario="diagnostic_repair_then_pass",
        idempotency_key="day9-conflict-key-99",
    )
    try:
        service.run(conflict)
        raised = False
    except IdempotencyConflictError:
        raised = True
    assert raised is True
    session.close()
