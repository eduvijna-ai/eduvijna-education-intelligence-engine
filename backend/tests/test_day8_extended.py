from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.exceptions import OrchestrationConfigurationError
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.anythingllm import AnythingLLMGenerationGateway
from app.orchestration.gateway.factory import build_generation_gateway
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.human_decision import HumanResumeDecision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_production_generation_gateway_requires_config() -> None:
    try:
        build_generation_gateway(
            Settings(
                anythingllm_base_url="",
                anythingllm_api_key="",
                anythingllm_orchestration_workspace="",
            ),
            force_fake=False,
        )
        raised = False
    except OrchestrationConfigurationError:
        raised = True
    assert raised


def test_author_gateway_failure_routes_failed() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(
            ctx, scenario="malformed_json", idempotency_key="author-fail-key"
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_human_resume_reject_does_not_complete() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-reject-key"
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    rejected = service.run(request, resume=HumanResumeDecision(action="reject"))
    assert rejected.status == OrchestrationRunStatus.FAILED
    session.close()


def test_anythingllm_generation_wire_request_shape() -> None:
    gateway = AnythingLLMGenerationGateway(
        "https://example.test",
        "secret-key",
        workspace_slug="orchestration-ws",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "chat-1",
        "textResponse": (
            '{"item_id":"i","stem_text":"x","question_type":"single_choice","options":[]}'
        ),
    }
    with patch.object(httpx.Client, "post", return_value=mock_response) as post:
        gateway.generate(
            GenerationRequest(
                role=GenerationNodeRole.AUTHOR,
                prompt_version="author@v1",
                system_prompt="system",
                user_payload={"item_id": "i"},
                output_schema_name="DraftQuestionItem",
            )
        )
    body = post.call_args.kwargs.get("json") or post.call_args[1].get("json")
    assert "systemPrompt" not in body
    assert "author@v1" in body["message"]
    assert body["mode"] == "chat"


def test_anythingllm_empty_response_is_gateway_failure() -> None:
    gateway = AnythingLLMGenerationGateway(
        "https://example.test",
        "secret-key",
        workspace_slug="orchestration-ws",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "chat-1", "textResponse": ""}
    with patch.object(httpx.Client, "post", return_value=mock_response):
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
            assert exc.code == "gateway_invalid_json"
    assert raised


def test_sqlite_checkpoint_survives_service_rebuild() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        app_db_path = str(Path(tmpdir) / "orch.db")
        checkpoint_db_path = str(Path(tmpdir) / "checkpoint.db")
        engine = create_engine(f"sqlite:///{app_db_path}")
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        file_settings = Settings(database_url=f"sqlite:///{app_db_path}")
        checkpoint_settings = Settings(database_url=f"sqlite:///{checkpoint_db_path}")
        with Session(engine) as session:
            ki_adapter = FakeAnythingLLMAdapter()
            ctx = seed_day8_fixtures(session, adapter=ki_adapter)
            service = build_orchestration_service(
                session,
                settings=file_settings,
                knowledge_adapter=ki_adapter,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
                force_fake=True,
            )
            request = build_orchestration_request(
                ctx, scenario="human_review", idempotency_key="persist-hitl-key"
            )
            paused = service.run(request)
            assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
            calls_before = len(service.dependencies.gateway.call_history())
            service.close()

            rebuilt = build_orchestration_service(
                session,
                settings=file_settings,
                knowledge_adapter=ki_adapter,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
                force_fake=True,
            )
            try:
                completed = rebuilt.run(
                    request, resume=HumanResumeDecision(action="approve")
                )
                calls_after = len(rebuilt.dependencies.gateway.call_history())
                assert completed.status == OrchestrationRunStatus.COMPLETED
                assert calls_before > 0
                assert calls_after == 0
            finally:
                rebuilt.close()
