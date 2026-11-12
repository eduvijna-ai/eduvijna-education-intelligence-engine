from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.orchestration import (
    OrchestrationAuditEvent,
    OrchestrationGenerationCall,
    OrchestrationIdempotencyRecord,
)
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import build_orchestration_request, seed_day8_fixtures
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision


def _row_count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _worker(db_path: Path, state_path: Path, phase: str) -> None:
    """Run in an independent Python interpreter, never a reused session."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    settings = Settings(database_url=url)
    gateway = FakeGenerationGateway()
    adapter = FakeAnythingLLMAdapter()

    with Session(engine) as session:
        if phase == "pause":
            ctx = seed_day8_fixtures(session, adapter=adapter)
            request = build_orchestration_request(
                ctx,
                scenario="human_review",
                idempotency_key="d11-process-restart-001",
            )
        else:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            request = OrchestrationRequest.model_validate(previous["request"])

        managed = build_managed_checkpointer(settings, memory_only=False)
        service = build_orchestration_service(
            session,
            gateway=gateway,
            knowledge_adapter=adapter,
            checkpointer=managed,
            force_fake=True,
        )
        try:
            if phase == "pause":
                result = service.run(request)
                assert result.status == OrchestrationRunStatus.REVIEW_REQUIRED
                generation_calls = _row_count(session, OrchestrationGenerationCall)
                # The fake gateway is tracked in memory; the persistent
                # generation-call cache may legitimately have zero rows.
                assert len(gateway.call_history()) > 0
                state_path.write_text(
                    json.dumps(
                        {
                            "request": request.model_dump(mode="json"),
                            "run_id": result.run_id,
                            "generation_calls": generation_calls,
                            "audit_count": _row_count(session, OrchestrationAuditEvent),
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            elif phase == "resume":
                result = service.run(
                    request, resume=HumanResumeDecision(action="approve")
                )
                assert result.status == OrchestrationRunStatus.COMPLETED
                assert result.run_id == previous["run_id"]
                assert len(gateway.call_history()) == 0
                assert _row_count(session, OrchestrationGenerationCall) == previous[
                    "generation_calls"
                ]
                audit_before = _row_count(session, OrchestrationAuditEvent)
                completed = service.run(request)
                assert completed.status == OrchestrationRunStatus.COMPLETED
                assert completed.run_id == result.run_id
                assert completed.model_dump(mode="json") == result.model_dump(mode="json")
                assert _row_count(session, OrchestrationAuditEvent) == audit_before
                assert len(gateway.call_history()) == 0
                idempotency_rows = session.scalars(
                    select(OrchestrationIdempotencyRecord).where(
                        OrchestrationIdempotencyRecord.idempotency_key
                        == request.idempotency_key
                    )
                ).all()
                assert len(idempotency_rows) == 1
                assert idempotency_rows[0].status == "completed"
            else:
                raise AssertionError(f"unknown worker phase: {phase}")
        finally:
            service.close()
            session.commit()
    engine.dispose()


def test_day11_human_review_survives_independent_worker_process_restart() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        database = root / "day11-worker.db"
        state = root / "checkpoint-result.json"
        for phase in ("pause", "resume"):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(database), str(state), phase],
                check=False,
                capture_output=True,
                text=True,
                timeout=80,
            )
            assert completed.returncode == 0, (
                f"Day11 {phase} process failed:\n"
                f"stdout={completed.stdout[-2500:]}\n"
                f"stderr={completed.stderr[-5000:]}"
            )
        assert state.exists()
        assert Path(str(database) + ".langgraph.sqlite").exists()


if __name__ == "__main__":
    _worker(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
