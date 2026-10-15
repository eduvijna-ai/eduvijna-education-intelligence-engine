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


def test_multi_item_batch_one_repaired_sibling() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    def _author_calls(gw: FakeGenerationGateway) -> int:
        return len(
            [
                c
                for c in gw.call_history()
                if c.call_context and c.call_context.role.value == "author"
            ]
        )

    before_author_calls = _author_calls(gateway)
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
    stems = {item.stem_text for item in result.items}
    assert len(stems) == 2
    after_author_calls = _author_calls(gateway)
    assert after_author_calls == before_author_calls + 2
    session.close()
