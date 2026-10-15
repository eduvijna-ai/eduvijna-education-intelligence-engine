from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
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


def test_two_item_batch_preserves_passing_sibling() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        diagnostic_scenario="diagnostic_clean_pass",
        idempotency_key="day9-batch-multi",
        requested_count=2,
    )
    result = service.run(request)
    assert result.status == OrchestrationRunStatus.COMPLETED
    assert result.approved_count == 2
    assert result.requested_count == 2
    assert len(result.items) == 2
    slot0 = next(item for item in result.items if item.slot_index == 0)
    slot1 = next(item for item in result.items if item.slot_index == 1)
    assert slot0.stem_text != slot1.stem_text
    counts = _role_counts(gateway)
    assert counts.get("author", 0) == 2
    assert counts.get("solver", 0) == 2
    diag_calls = [
        c
        for c in gateway.call_history()
        if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
    ]
    assert len(diag_calls) >= 2
    diag_results = {
        entry["item_id"]: entry
        for entry in (result.metadata_json.get("diagnostic_results") or [])
    }
    assert diag_results[slot0.item_id]["aggregate_status"] == "pass"
    assert diag_results[slot1.item_id]["aggregate_status"] == "pass"
    slot0_calls = [
        c
        for c in diag_calls
        if c.call_context and c.call_context.item_id == slot0.item_id
    ]
    assert len(slot0_calls) == 1
    session.close()
