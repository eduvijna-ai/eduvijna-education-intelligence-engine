from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import build_orchestration_request, seed_day8_fixtures
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError
from app.orchestration.service import OrchestrationService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _service(session: Session, gateway=None):
    adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=adapter)
    service = OrchestrationService(
        session,
        gateway=gateway,
        ki_adapter=adapter,
        memory_checkpointer=True,
    )
    return ctx, service


def test_malformed_json_gateway_fails() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = _service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(
            ctx, scenario="malformed_json", idempotency_key="malformed-json-key"
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_solver_disagreement_routes_to_failure_or_repair() -> None:
    session = _session()
    ctx, service = _service(session)
    result = service.run(
        build_orchestration_request(
            ctx, scenario="solver_disagree", idempotency_key="solver-disagree-key"
        )
    )
    assert result.status != OrchestrationRunStatus.COMPLETED or result.approved_count == 0
    session.close()


def test_bad_provenance_rejected() -> None:
    session = _session()
    ctx, service = _service(session)
    result = service.run(
        build_orchestration_request(
            ctx, scenario="bad_provenance", idempotency_key="bad-prov-key"
        )
    )
    assert result.approved_count == 0
    session.close()


def test_duplicate_output_rejected() -> None:
    session = _session()
    ctx, service = _service(session)
    request = build_orchestration_request(
        ctx,
        scenario="duplicate",
        idempotency_key="duplicate-key",
        requested_count=2,
    )
    result = service.run(request)
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_gateway_errors_structured() -> None:
    gateway = FakeGenerationGateway()
    from app.orchestration.enums import GenerationNodeRole
    from app.orchestration.gateway.types import GenerationRequest

    for scenario, code in [
        ("gateway_timeout", "gateway_timeout"),
        ("gateway_401", "gateway_unauthorized"),
        ("gateway_5xx", "gateway_unavailable"),
    ]:
        try:
            gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.AUTHOR,
                    prompt_version="author@v1",
                    system_prompt="x",
                    user_payload={"item_id": "i"},
                    output_schema_name="DraftQuestionItem",
                    scenario=scenario,
                )
            )
        except GenerationGatewayError as exc:
            assert exc.code == code
