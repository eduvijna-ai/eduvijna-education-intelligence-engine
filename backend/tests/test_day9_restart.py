from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.checkpoint_proof import (
    prove_interrupted_diagnostic_checkpoint_restart,
)
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_diagnostic_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.fake import FakeGenerationGateway


def test_completed_idempotent_replay_is_not_restart() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    ki = FakeAnythingLLMAdapter()
    gateway_a = FakeGenerationGateway()
    with Session(engine) as session:
        ctx = seed_day8_fixtures(session, adapter=ki)
        service_a = build_orchestration_service(
            session,
            gateway=gateway_a,
            knowledge_adapter=ki,
            force_fake=True,
        )
        request = build_diagnostic_orchestration_request(
            ctx,
            idempotency_key="day9-durable-diag-replay",
        )
        first = service_a.run(request)
        session.commit()
        diag_a = len(
            [
                c
                for c in gateway_a.call_history()
                if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
            ]
        )
        service_a.close()

    gateway_b = FakeGenerationGateway()
    with Session(engine) as session:
        service_b = build_orchestration_service(
            session,
            gateway=gateway_b,
            knowledge_adapter=ki,
            force_fake=True,
        )
        second = service_b.run(request)
        diag_b = len(
            [
                c
                for c in gateway_b.call_history()
                if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
            ]
        )
        assert first.status == OrchestrationRunStatus.COMPLETED
        assert second.status == OrchestrationRunStatus.COMPLETED
        assert first.run_id == second.run_id
        assert diag_a >= 1
        assert diag_b == 0
        service_b.close()


def test_file_backed_checkpoint_restart_reuses_diagnostic_calls() -> None:
    assert prove_interrupted_diagnostic_checkpoint_restart() is True
