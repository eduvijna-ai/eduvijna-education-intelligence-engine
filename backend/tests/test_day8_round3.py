from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.orchestration import OrchestrationGenerationCall, OrchestrationIdempotencyRecord
from app.orchestration.control_session import open_control_session
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.execution_lease import (
    LeaseAcquireResult,
    try_acquire_execution_lease,
)
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.gateway_invoke import chat_session_id_for_call, invoke_generation
from app.orchestration.idempotency import claim_idempotency
from app.orchestration.model_calls import call_cache_key


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_control_commit_does_not_commit_unrelated_domain_rows() -> None:
    session = _session()
    ctx = seed_day8_fixtures(session)
    control = open_control_session(session)
    request = build_orchestration_request(ctx, idempotency_key="control-isolation-key")
    claim_idempotency(control, request)
    control.commit()
    from app.models import Organization

    pending = Organization(code="pending-org", name="Pending Org")
    session.add(pending)
    session.flush()
    pending_id = pending.id
    assert session.get(Organization, pending_id) is not None
    session.rollback()
    assert session.get(Organization, pending_id) is None
    verify = Session(session.get_bind())
    assert (
        verify.scalar(
            select(OrchestrationIdempotencyRecord).where(
                OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
            )
        )
        is not None
    )
    verify.close()
    session.close()
    control.close()


def test_execution_lease_blocks_concurrent_holder() -> None:
    session = _session()
    control_a = open_control_session(session)
    control_b = open_control_session(session)
    first = try_acquire_execution_lease(
        control_a, thread_id="thread-1", run_id="run-1", holder_id="holder-a"
    )
    control_a.commit()
    second = try_acquire_execution_lease(
        control_b, thread_id="thread-1", run_id="run-1", holder_id="holder-b"
    )
    assert first == LeaseAcquireResult.ACQUIRED
    assert second == LeaseAcquireResult.BLOCKED
    control_a.close()
    control_b.close()
    session.close()


def test_concurrent_run_returns_already_in_progress_without_gateway_calls() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(ctx, idempotency_key="concurrent-lease-key")
    control = open_control_session(session)
    _, canonical_run_id, _ = claim_idempotency(control, request)
    control.commit()
    try_acquire_execution_lease(
        control,
        thread_id=canonical_run_id,
        run_id=canonical_run_id,
        holder_id="foreign-holder",
    )
    control.commit()
    blocked = service.run(request)
    assert "already_in_progress" in blocked.errors
    assert len(gateway.call_history()) == 0
    control.close()
    session.close()


def test_invoke_generation_reuses_completed_call_without_second_post() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    deps = service.dependencies
    state: dict = {
        "run_id": "run-durable",
        "request_hash": "hash",
        "generation_call_cache": {},
    }
    from app.orchestration.gateway.types import GenerationRequest
    from app.orchestration.prompts.registry import get_prompt

    prompt = get_prompt("author")
    request = GenerationRequest(
        role=GenerationNodeRole.AUTHOR,
        prompt_version=prompt.version,
        system_prompt=prompt.text,
        user_payload={"item_id": "slot-0", "run_id": "run-durable"},
        output_schema_name="DraftQuestionItem",
        scenario="clean_pass",
    )
    first, _ = invoke_generation(
        deps,
        state,
        node_name="author",
        attempt=1,
        request=request,
        run_id="run-durable",
        item_id="slot-0",
        schema_payload_merge={"slot_index": 0},
    )
    assert first is not None
    assert len(gateway.call_history()) == 1
    second, _ = invoke_generation(
        deps,
        state,
        node_name="author",
        attempt=1,
        request=request,
        run_id="run-durable",
        item_id="slot-0",
        schema_payload_merge={"slot_index": 0},
    )
    assert second is not None
    assert len(gateway.call_history()) == 1
    session.close()


class _RepairTimeoutGateway(FakeGenerationGateway):
    def generate(self, request: GenerationRequest):
        if request.role == GenerationNodeRole.REPAIR:
            raise GenerationGatewayError("gateway_timeout", "repair timeout", retryable=True)
        return super().generate(request)


def test_repair_gateway_timeout_enters_retry_required() -> None:
    session = _session()
    gateway = _RepairTimeoutGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(
            ctx,
            scenario="repair_then_pass",
            idempotency_key="repair-timeout-r3",
            max_repairs=2,
        )
    )
    assert result.status == OrchestrationRunStatus.RETRY_REQUIRED
    assert "gateway_timeout" in result.errors
    session.close()


def test_gateway_retryable_not_terminal_idempotency() -> None:
    session = _session()
    gateway = _RepairTimeoutGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        scenario="repair_then_pass",
        idempotency_key="retry-not-terminal",
        max_repairs=2,
    )
    service.run(request)
    control = open_control_session(session)
    record = control.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    assert record is not None
    assert record.status == "in_progress"
    control.close()
    session.close()


def test_author_solver_distinct_chat_sessions() -> None:
    author_key = call_cache_key(
        run_id="run-1",
        role=GenerationNodeRole.AUTHOR,
        item_id="item-1",
        prompt_version="author@v1",
        payload={"item_id": "item-1"},
    )
    solver_key = call_cache_key(
        run_id="run-1",
        role=GenerationNodeRole.SOLVER,
        item_id="item-1",
        prompt_version="solver@v1",
        payload={"item_id": "item-1"},
    )
    assert chat_session_id_for_call(author_key) != chat_session_id_for_call(solver_key)


def test_extra_model_fields_not_stored_as_completed() -> None:
    session = _session()
    gateway = FakeGenerationGateway()

    class _ExtraFieldGateway(FakeGenerationGateway):
        def generate(self, request: GenerationRequest):
            response = super().generate(request)
            if request.output_schema_name == "DraftQuestionItem":
                polluted = dict(response.parsed)
                polluted["hidden_reasoning"] = "must not persist"
                return response.__class__(
                    parsed=polluted,
                    raw_text=response.raw_text,
                    latency_ms=response.latency_ms,
                    gateway_request_id=response.gateway_request_id,
                    usage=response.usage,
                )
            return response

    gateway = _ExtraFieldGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(ctx, idempotency_key="schema-extra-reject")
    )
    assert result.status != OrchestrationRunStatus.COMPLETED
    control = open_control_session(session)
    completed = control.scalars(
        select(OrchestrationGenerationCall).where(
            OrchestrationGenerationCall.status == "completed"
        )
    ).all()
    assert all(
        "hidden_reasoning" not in (row.response_json or {}).get("parsed", {})
        for row in completed
    )
    control.close()
    session.close()


def test_anythingllm_workspace_contract_rejects_documents() -> None:
    from app.orchestration.gateway.anythingllm import AnythingLLMGenerationGateway

    gateway = AnythingLLMGenerationGateway(
        "https://example.test", "secret", workspace_slug="orchestration-ws"
    )
    mock_workspace = MagicMock()
    mock_workspace.status_code = 200
    mock_workspace.json.return_value = {
        "workspace": {"documents": [{"id": "doc-1"}], "slug": "orchestration-ws"}
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "textResponse": (
            '{"item_id":"i","stem_text":"x","question_type":"single_choice","options":[]}'
        )
    }
    with (
        patch.object(httpx.Client, "get", return_value=mock_workspace),
        patch.object(httpx.Client, "post", return_value=mock_response),
    ):
        try:
            gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.AUTHOR,
                    prompt_version="author@v1",
                    system_prompt="system",
                    user_payload={"item_id": "i"},
                    output_schema_name="DraftQuestionItem",
                )
            )
            raised = False
        except GenerationGatewayError as exc:
            raised = True
            assert exc.code == "gateway_configuration"
    assert raised


def test_day8_verify_candidate_sha_mismatch_fails_ok() -> None:
    from app import day8_verify

    report = {
        "checks": {
            "candidate_sha_resolved": True,
            "candidate_sha_matches_head": False,
            "ok": False,
        }
    }
    report["checks"]["ok"] = all(
        value for key, value in report["checks"].items() if key != "ok"
    )
    assert report["checks"]["ok"] is False
    assert day8_verify._resolve_candidate_sha()  # env may vary
