"""Executable interrupted-checkpoint proof for Day 9 verifier (D9-R2-05 / D9-R2-06)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import build_diagnostic_orchestration_request, seed_day8_fixtures
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import (
    GenerationGatewayError,
    GenerationRequest,
    GenerationResponse,
)


class _FailSecondDiagnosticGateway:
    """Complete the first diagnostic call, fail the second with a retryable gateway error."""

    def __init__(self, inner: FakeGenerationGateway) -> None:
        self._inner = inner
        self._diagnostic_calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if request.role == GenerationNodeRole.DIAGNOSTIC:
            self._diagnostic_calls += 1
            if self._diagnostic_calls >= 2:
                raise GenerationGatewayError(
                    "gateway_timeout",
                    "simulated interrupt before second diagnostic completes",
                    retryable=True,
                )
        return self._inner.generate(request)

    def call_history(self) -> list[GenerationResponse]:
        return self._inner.call_history()


def _diagnostic_call_count(gateway: FakeGenerationGateway) -> int:
    return len(
        [
            call
            for call in gateway.call_history()
            if call.call_context and call.call_context.role == GenerationNodeRole.DIAGNOSTIC
        ]
    )


def prove_interrupted_diagnostic_checkpoint_restart() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "orchestration.sqlite"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url)
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        settings = Settings(database_url=database_url)
        ki = FakeAnythingLLMAdapter()
        inner = FakeGenerationGateway()
        gateway = _FailSecondDiagnosticGateway(inner)

        with Session(engine) as session:
            ctx = seed_day8_fixtures(session, adapter=ki)
            request = build_diagnostic_orchestration_request(
                ctx,
                diagnostic_scenario="diagnostic_repair_then_pass",
                idempotency_key="day9-checkpoint-restart-proof",
                requested_count=1,
            )
            service_a = build_orchestration_service(
                session,
                settings,
                gateway=gateway,
                knowledge_adapter=ki,
                force_fake=True,
                memory_checkpointer=False,
            )
            interrupted = service_a.run(request)
            session.commit()
            calls_after_interrupt = _diagnostic_call_count(inner)
            service_a.close()

        if interrupted.status != OrchestrationRunStatus.RETRY_REQUIRED:
            return False
        if calls_after_interrupt < 1:
            return False

        inner_b = FakeGenerationGateway()
        with Session(engine) as session:
            service_b = build_orchestration_service(
                session,
                settings,
                gateway=inner_b,
                knowledge_adapter=ki,
                force_fake=True,
                memory_checkpointer=False,
            )
            resumed = service_b.run(request, allow_gateway_retry=True)
            session.commit()
            calls_on_resume = _diagnostic_call_count(inner_b)
            service_b.close()

        return (
            resumed.status == OrchestrationRunStatus.COMPLETED
            and resumed.approved_count == 1
            and calls_on_resume >= 1
        )
