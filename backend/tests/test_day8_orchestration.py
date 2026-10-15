from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import build_orchestration_request, seed_day8_fixtures
from app.orchestration.graph import build_orchestration_graph
from app.orchestration.scope_guard import verify_day8_scope_guard
from app.orchestration.service import OrchestrationService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _service(session: Session) -> tuple[dict[str, str], OrchestrationService]:
    adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=adapter)
    service = OrchestrationService(session, ki_adapter=adapter, memory_checkpointer=True)
    return ctx, service


def test_day8_graph_compiles_and_clean_pass() -> None:
    session = _session()
    ctx, service = _service(session)
    graph = build_orchestration_graph(service.dependencies, checkpointer=service._checkpointer)
    assert graph is not None
    result = service.run(build_orchestration_request(ctx, scenario="clean_pass"))
    assert result.status == OrchestrationRunStatus.COMPLETED
    assert result.approved_count == 1
    assert result.source_revision_ids
    session.close()


def test_day8_repair_then_pass() -> None:
    session = _session()
    ctx, service = _service(session)
    result = service.run(
        build_orchestration_request(
            ctx, scenario="repair_then_pass", idempotency_key="repair-pass-key"
        )
    )
    assert result.status == OrchestrationRunStatus.COMPLETED
    session.close()


def test_day8_idempotent_replay() -> None:
    session = _session()
    ctx, service = _service(session)
    request = build_orchestration_request(ctx, idempotency_key="idem-key-12345678")
    first = service.run(request)
    second = service.run(request)
    assert first.run_id == second.run_id
    session.close()


def test_day8_scope_guard_no_provider_imports() -> None:
    report = verify_day8_scope_guard()
    assert report["ok"] is True
