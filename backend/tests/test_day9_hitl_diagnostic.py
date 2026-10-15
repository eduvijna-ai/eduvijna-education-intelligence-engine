from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision


def _diag_calls(gateway: FakeGenerationGateway) -> int:
    return len(
        [
            c
            for c in gateway.call_history()
            if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
        ]
    )


def test_hitl_approve_routes_to_diagnostic_enrichment() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        scenario="human_review",
        idempotency_key="day9-hitl-diagnostic",
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    assert _diag_calls(gateway) == 0
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED
    assert _diag_calls(gateway) >= 1
    assert completed.metadata_json.get("diagnostic_results")
    session.close()

