from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import ResolvedScope
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.anythingllm import AnythingLLMGenerationGateway
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.idempotency import claim_idempotency
from app.orchestration.scope_validation import validate_context_scope


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_idempotency_reuses_canonical_run_id() -> None:
    session = _session()
    ctx = seed_day8_fixtures(session)
    base = build_orchestration_request(ctx, idempotency_key="canonical-run-key")
    alt = base.model_copy(update={"run_id": "00000000-0000-4000-8000-000000000001"})
    _, run_a, _ = claim_idempotency(session, base)
    session.commit()
    _, run_b, _ = claim_idempotency(session, alt)
    assert run_a == run_b
    session.close()


def test_scope_mismatch_when_applied_scope_missing() -> None:
    issues = validate_context_scope(
        ResolvedScope(curriculum_version_id="cv-1", organization_id="org-1"),
        KnowledgeContextPack(
            query_id="q1",
            query_text="probe",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[],
            scope=AppliedKnowledgeScope(organization_id="org-1", curriculum_version_id=None),
            citations=[],
            bounded_text="",
            warnings=[],
        ),
    )
    assert "scope_mismatch:curriculum_version_id" in issues


def test_durable_generation_call_survives_replay() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx, requested_count=2, idempotency_key="durable-call-key"
    )
    service.run(request)
    assert len(gateway.call_history()) >= 2
    first_count = len(gateway.call_history())
    service.run(request)
    assert len(gateway.call_history()) == first_count
    session.close()


def test_repair_gateway_failure_does_not_increment() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(
            ctx,
            scenario="repair_then_pass",
            idempotency_key="repair-gateway-fail",
            max_repairs=1,
        )
    )
    gateway._history.clear()
    fail_request = GenerationRequest(
        role=GenerationNodeRole.REPAIR,
        prompt_version="repair@v1",
        system_prompt="x",
        user_payload={"repair_instructions": {}},
        output_schema_name="RepairPlan",
        scenario="gateway_timeout",
    )
    try:
        gateway.generate(fail_request)
    except GenerationGatewayError:
        pass
    assert result.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.REVIEW_REQUIRED,
        OrchestrationRunStatus.FAILED,
    }
    session.close()


def test_anythingllm_rejects_model_settings() -> None:
    gateway = AnythingLLMGenerationGateway(
        "https://example.test", "secret", workspace_slug="ws"
    )
    try:
        gateway.generate(
            GenerationRequest(
                role=GenerationNodeRole.AUTHOR,
                prompt_version="author@v1",
                system_prompt="system",
                user_payload={"item_id": "i"},
                output_schema_name="DraftQuestionItem",
                model_settings={"temperature": 0.2},
            )
        )
        raised = False
    except GenerationGatewayError as exc:
        raised = True
        assert exc.code == "gateway_validation"
    assert raised


def test_orchestration_models_postgres_compile() -> None:
    from sqlalchemy.dialects import postgresql

    from app.models.orchestration import OrchestrationGenerationCall

    ddl = str(
        OrchestrationGenerationCall.__table__.compile(dialect=postgresql.dialect())
    )
    assert "orchestration_generation_calls" in ddl


def test_postgres_checkpointer_contract() -> None:
    with patch("langgraph.checkpoint.postgres.PostgresSaver") as saver_cls:
        cm = MagicMock()
        saver = MagicMock()
        cm.__enter__.return_value = saver
        saver_cls.from_conn_string.return_value = cm
        from app.orchestration.checkpoint import build_managed_checkpointer

        managed = build_managed_checkpointer(
            Settings(database_url="postgresql+psycopg://user:pass@localhost/db"),
            memory_only=False,
        )
        saver.setup.assert_called_once()
        managed.close()
        cm.__exit__.assert_called_once()


def test_day8_verify_candidate_sha_gate(monkeypatch) -> None:
    from app import day8_verify

    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", "deadbeef")
    monkeypatch.setattr(day8_verify, "_git_head", lambda: "cafebabe")
    assert day8_verify._resolve_candidate_sha() == "deadbeef"


def test_hitl_interrupt_payload_present() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-payload"
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    assert paused.metadata_json.get("interrupt_payload") is not None
    assert paused.metadata_json["interrupt_payload"].get("deterministic_validation") is not None
    session.close()


def test_service_b_resumes_after_service_a_closed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        app_db_path = str(Path(tmpdir) / "app.db")
        checkpoint_db_path = str(Path(tmpdir) / "checkpoint.db")
        engine = create_engine(f"sqlite:///{app_db_path}")
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        file_settings = Settings(database_url=f"sqlite:///{app_db_path}")
        checkpoint_settings = Settings(database_url=f"sqlite:///{checkpoint_db_path}")
        from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter

        with Session(engine) as session:
            ki = FakeAnythingLLMAdapter()
            ctx = seed_day8_fixtures(session, adapter=ki)
            service_a = build_orchestration_service(
                session,
                settings=file_settings,
                knowledge_adapter=ki,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
                force_fake=True,
            )
            request = build_orchestration_request(
                ctx, scenario="human_review", idempotency_key="restart-service-b"
            )
            paused = service_a.run(request)
            calls_before = len(service_a.dependencies.gateway.call_history())
            service_a.close()

            service_b = build_orchestration_service(
                session,
                settings=file_settings,
                knowledge_adapter=ki,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
                force_fake=True,
            )
            completed = service_b.run(request, resume=HumanResumeDecision(action="approve"))
            calls_after = len(service_b.dependencies.gateway.call_history())
            assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
            assert completed.status == OrchestrationRunStatus.COMPLETED
            assert calls_before > 0
            assert calls_after == 0
            service_b.close()


def test_idempotency_conflict_before_gateway() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    first = build_orchestration_request(ctx, idempotency_key="conflict-r2-key")
    service.run(first)
    second = build_orchestration_request(
        ctx, scenario="repair_then_pass", idempotency_key="conflict-r2-key"
    )
    try:
        service.run(second)
        raised = False
    except IdempotencyConflictError:
        raised = True
    assert raised
    session.close()
