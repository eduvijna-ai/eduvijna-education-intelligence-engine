from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)


def test_multi_item_batch_preserves_cardinality_and_diagnostic_metadata() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ctx, service = build_day8_test_service(session)
    first = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-batch-item-a",
            requested_count=1,
        )
    )
    second = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_repair_then_pass",
            idempotency_key="day9-batch-item-b",
            requested_count=1,
        )
    )
    assert first.status == OrchestrationRunStatus.COMPLETED
    assert second.status == OrchestrationRunStatus.COMPLETED
    assert len(first.metadata_json.get("diagnostic_results") or []) == 1
    assert len(second.metadata_json.get("diagnostic_results") or []) == 1
    session.close()
