from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _service(session: Session, gateway=None):
    return build_day8_test_service(session, gateway=gateway)


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


def test_idempotency_conflict() -> None:
    session = _session()
    ctx, service = _service(session)
    first = build_orchestration_request(ctx, idempotency_key="conflict-key-123456")
    service.run(first)
    second = build_orchestration_request(
        ctx, scenario="repair_then_pass", idempotency_key="conflict-key-123456"
    )
    try:
        service.run(second)
        raised = False
    except IdempotencyConflictError:
        raised = True
    assert raised
    session.close()
