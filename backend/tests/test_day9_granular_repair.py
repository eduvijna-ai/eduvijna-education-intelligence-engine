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
from app.orchestration.gateway.fake import FakeGenerationGateway


def _role_counts(gateway: FakeGenerationGateway) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in gateway.call_history():
        if call.call_context is None:
            continue
        role = call.call_context.role.value
        counts[role] = counts.get(role, 0) + 1
    return counts


def test_tag_only_diagnostic_repair_does_not_reauthor() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        diagnostic_scenario="diagnostic_repair_then_pass",
        idempotency_key="day9-granular-repair",
    )
    result = service.run(request)
    assert result.status == OrchestrationRunStatus.COMPLETED
    counts = _role_counts(gateway)
    assert counts.get("author", 0) == 1
    assert counts.get("solver", 0) == 1
    option_texts = {o.option_key: o.text for o in result.items[0].options}
    assert option_texts["B"] == "12"
    session.close()
