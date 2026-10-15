from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.models.curriculum import CurriculumNode, CurriculumVersion
from app.models.enums import CurriculumNodeType
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import ResolvedScope
from app.orchestration.control_session import open_control_session
from app.orchestration.curriculum_scope import validate_curriculum_hierarchy
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.execution_lease import try_acquire_execution_lease
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.anythingllm import AnythingLLMGenerationGateway
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.gateway.workspace_contract import (
    ORCHESTRATION_WORKSPACE_PROMPT_MARKER,
    verify_orchestration_workspace,
)
from app.orchestration.gateway_invoke import invoke_generation
from app.orchestration.generation_call_store import (
    claim_generation_call_start,
    mark_generation_call_ambiguous,
)
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.model_calls import call_cache_key


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


class _FailOnceAuthorGateway(FakeGenerationGateway):
    def __init__(self, code: str) -> None:
        super().__init__()
        self._code = code
        self._failed = False

    def generate(self, request: GenerationRequest):
        if request.role == GenerationNodeRole.AUTHOR and not self._failed:
            self._failed = True
            raise GenerationGatewayError(
                self._code,
                "synthetic retryable failure",
                retryable=True,
                http_status=503 if self._code == "gateway_unavailable" else None,
            )
        return super().generate(request)


@pytest.mark.parametrize("code", ["gateway_timeout", "gateway_unavailable"])
def test_explicit_gateway_retry_recovers_retryable_author_failure(code: str) -> None:
    session = _session()
    gateway = _FailOnceAuthorGateway(code)
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        idempotency_key=f"explicit-retry-{code}",
    )
    first = service.run(request)
    assert first.status == OrchestrationRunStatus.RETRY_REQUIRED
    second = service.run(request, allow_gateway_retry=True)
    assert second.status == OrchestrationRunStatus.COMPLETED
    assert second.approved_count == 1
    service.close()
    session.close()


class _CrashBeforeRetryResponseGateway(FakeGenerationGateway):
    def generate(self, request: GenerationRequest):
        raise SystemExit("synthetic process crash during explicitly authorized retry")


def test_retry_authorization_audit_is_durable_before_external_side_effect(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "retry-audit.db"
    engine = create_engine(f"sqlite:///{db_path}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        gateway = _CrashBeforeRetryResponseGateway()
        ctx, service = build_day8_test_service(session, gateway=gateway)
        run_id = "retry-audit-run"
        request = GenerationRequest(
            role=GenerationNodeRole.AUTHOR,
            prompt_version="author@v1",
            system_prompt="system",
            user_payload={"run_id": run_id, "item_id": "slot-0"},
            output_schema_name="DraftQuestionItem",
        )
        key = call_cache_key(
            run_id=run_id,
            role=request.role,
            item_id="slot-0",
            prompt_version=request.prompt_version,
            payload=request.user_payload,
        )
        claim_generation_call_start(
            service.dependencies.control_session,
            run_id=run_id,
            cache_key=key,
            commit=True,
        )
        mark_generation_call_ambiguous(
            service.dependencies.control_session,
            run_id=run_id,
            cache_key=key,
            commit=True,
        )
        state = {
            "run_id": run_id,
            "request_hash": "retry-audit-hash",
            "generation_call_cache": {},
            "allow_gateway_retry": True,
        }
        with pytest.raises(SystemExit):
            invoke_generation(
                service.dependencies,
                state,  # type: ignore[arg-type]
                node_name="author",
                attempt=2,
                request=request,
                run_id=run_id,
                item_id="slot-0",
            )

        verify = open_control_session(session)
        event = verify.scalar(
            select(OrchestrationAuditEvent).where(
                OrchestrationAuditEvent.run_id == run_id,
                OrchestrationAuditEvent.status == "retry_authorized",
            )
        )
        assert event is not None
        verify.close()
        service.close()


def test_concurrent_explicit_retry_does_not_mutate_checkpoint_or_call_gateway() -> None:
    session = _session()
    gateway = _FailOnceAuthorGateway("gateway_timeout")
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(ctx, idempotency_key="retry-lease-blocked")
    first = service.run(request)
    assert first.status == OrchestrationRunStatus.RETRY_REQUIRED
    config = {"configurable": {"thread_id": first.run_id}}
    before = dict(service.compiled_graph.get_state(config).values)
    control = open_control_session(session)
    try_acquire_execution_lease(
        control,
        thread_id=first.run_id,
        run_id=first.run_id,
        holder_id="foreign-holder",
    )
    control.commit()
    calls_before = len(gateway.call_history())
    blocked = service.run(request, allow_gateway_retry=True)
    after = dict(service.compiled_graph.get_state(config).values)
    assert "already_in_progress" in blocked.errors
    assert calls_before == len(gateway.call_history())
    assert before == after
    control.close()
    service.close()
    session.close()


def _workspace_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


@pytest.mark.parametrize(
    "payload",
    [
        {
            "workspace": {
                "slug": "orchestration-ws",
                "openAiPrompt": ORCHESTRATION_WORKSPACE_PROMPT_MARKER,
            }
        },
        {"workspace": "unexpected"},
    ],
)
def test_workspace_contract_fails_closed_when_zero_documents_not_proven(
    payload: dict,
) -> None:
    with patch.object(httpx.Client, "get", return_value=_workspace_response(payload)):
        with pytest.raises(GenerationGatewayError) as exc:
            verify_orchestration_workspace(
                base_url="https://example.test",
                api_key="secret",
                workspace_slug="orchestration-ws",
            )
    assert exc.value.code == "gateway_configuration"


def test_workspace_contract_requires_trusted_guard_marker() -> None:
    payload = {
        "workspace": [
            {
                "slug": "orchestration-ws",
                "documents": [],
                "openAiPrompt": "generic workspace prompt",
            }
        ]
    }
    with patch.object(httpx.Client, "get", return_value=_workspace_response(payload)):
        with pytest.raises(GenerationGatewayError) as exc:
            verify_orchestration_workspace(
                base_url="https://example.test",
                api_key="secret",
                workspace_slug="orchestration-ws",
            )
    assert exc.value.code == "gateway_configuration"


def test_gateway_rejects_workspace_switch_after_verified_workspace() -> None:
    gateway = AnythingLLMGenerationGateway(
        "https://example.test",
        "secret",
        workspace_slug="orchestration-ws",
    )
    workspace = _workspace_response(
        {
            "workspace": [
                {
                    "slug": "orchestration-ws",
                    "documents": [],
                    "openAiPrompt": (
                        f"{ORCHESTRATION_WORKSPACE_PROMPT_MARKER} trusted guard"
                    ),
                }
            ]
        }
    )
    chat = MagicMock()
    chat.status_code = 200
    chat.headers = {}
    chat.json.return_value = {
        "textResponse": (
            '{"item_id":"i","stem_text":"x","question_type":"single_choice","options":[]}'
        )
    }
    base_request = GenerationRequest(
        role=GenerationNodeRole.AUTHOR,
        prompt_version="author@v1",
        system_prompt="system",
        user_payload={"item_id": "i"},
        output_schema_name="DraftQuestionItem",
    )
    with (
        patch.object(httpx.Client, "get", return_value=workspace) as get,
        patch.object(httpx.Client, "post", return_value=chat),
    ):
        gateway.generate(base_request)
        with pytest.raises(GenerationGatewayError) as exc:
            gateway.generate(
                GenerationRequest(
                    role=base_request.role,
                    prompt_version=base_request.prompt_version,
                    system_prompt=base_request.system_prompt,
                    user_payload=base_request.user_payload,
                    output_schema_name=base_request.output_schema_name,
                    workspace_slug="other-workspace",
                )
            )
    assert exc.value.code == "gateway_configuration"
    assert get.call_count == 1


def test_nested_curriculum_topic_concept_ancestry_is_enforced() -> None:
    session = _session()
    ctx = seed_cbse_fixture_curriculum(session)
    version = session.get(CurriculumVersion, ctx["curriculum_version_id"])
    assert version is not None
    subject = session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id,
            CurriculumNode.node_type == CurriculumNodeType.SUBJECT.value,
            CurriculumNode.code == "mathematics",
        )
    )
    assert subject is not None
    unit = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.UNIT.value,
        code="algebra",
        title="Algebra",
    )
    chapter = CurriculumNode(
        curriculum_version=version,
        parent=unit,
        node_type=CurriculumNodeType.CHAPTER.value,
        code="linear-equations",
        title="Linear Equations",
    )
    topic = CurriculumNode(
        curriculum_version=version,
        parent=chapter,
        node_type=CurriculumNodeType.TOPIC.value,
        code="slope-topic",
        title="Slope",
    )
    concept = CurriculumNode(
        curriculum_version=version,
        parent=topic,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="slope-concept",
        title="Slope concept",
    )
    other_subject = CurriculumNode(
        curriculum_version=version,
        parent=subject.parent,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="science",
        title="Science",
    )
    foreign_topic = CurriculumNode(
        curriculum_version=version,
        parent=other_subject,
        node_type=CurriculumNodeType.TOPIC.value,
        code="foreign-topic",
        title="Foreign topic",
    )
    session.add_all([unit, chapter, topic, concept, other_subject, foreign_topic])
    session.flush()

    valid = ResolvedScope(
        curriculum_version_id=version.id,
        grade_year_code="grade-8",
        medium_code="english",
        subject_code="mathematics",
        topic_codes=["slope-topic"],
        concept_codes=["slope-concept"],
    )
    assert validate_curriculum_hierarchy(session, valid) == []

    wrong_subject = valid.model_copy(
        update={"topic_codes": ["foreign-topic"], "concept_codes": []}
    )
    assert "invalid_topic_code:foreign-topic" in validate_curriculum_hierarchy(
        session, wrong_subject
    )

    grade = subject.parent.parent if subject.parent is not None else None
    medium = subject.parent
    assert grade is not None
    assert medium is not None

    grade_nine = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="grade-9",
        title="Grade 9",
    )
    medium_nine = CurriculumNode(
        curriculum_version=version,
        parent=grade_nine,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="english",
        title="English",
    )
    subject_nine = CurriculumNode(
        curriculum_version=version,
        parent=medium_nine,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    grade_nine_topic = CurriculumNode(
        curriculum_version=version,
        parent=subject_nine,
        node_type=CurriculumNodeType.TOPIC.value,
        code="grade-nine-topic",
        title="Grade 9 topic",
    )
    telugu_medium = CurriculumNode(
        curriculum_version=version,
        parent=grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="telugu",
        title="Telugu",
    )
    telugu_subject = CurriculumNode(
        curriculum_version=version,
        parent=telugu_medium,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    telugu_topic = CurriculumNode(
        curriculum_version=version,
        parent=telugu_subject,
        node_type=CurriculumNodeType.TOPIC.value,
        code="telugu-topic",
        title="Telugu topic",
    )
    session.add_all(
        [
            grade_nine,
            medium_nine,
            subject_nine,
            grade_nine_topic,
            telugu_medium,
            telugu_subject,
            telugu_topic,
        ]
    )
    session.flush()

    wrong_grade = valid.model_copy(
        update={"topic_codes": ["grade-nine-topic"], "concept_codes": []}
    )
    assert "invalid_topic_code:grade-nine-topic" in validate_curriculum_hierarchy(
        session, wrong_grade
    )

    wrong_medium = valid.model_copy(
        update={"topic_codes": ["telugu-topic"], "concept_codes": []}
    )
    assert "invalid_topic_code:telugu-topic" in validate_curriculum_hierarchy(
        session, wrong_medium
    )

    pack = version.curriculum_pack
    other_version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="fixture-other",
        academic_year="2099-00",
        status="active",
    )
    session.add(other_version)
    session.flush()
    foreign_grade = CurriculumNode(
        curriculum_version=other_version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="grade-8",
        title="Grade 8 other",
    )
    foreign_medium = CurriculumNode(
        curriculum_version=other_version,
        parent=foreign_grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="english",
        title="English",
    )
    foreign_subject = CurriculumNode(
        curriculum_version=other_version,
        parent=foreign_medium,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    foreign_concept = CurriculumNode(
        curriculum_version=other_version,
        parent=foreign_subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="foreign-concept",
        title="Foreign concept",
    )
    session.add_all(
        [foreign_grade, foreign_medium, foreign_subject, foreign_concept]
    )
    session.flush()
    foreign_version_scope = valid.model_copy(
        update={"topic_codes": [], "concept_codes": ["foreign-concept"]}
    )
    assert "invalid_concept_code:foreign-concept" in validate_curriculum_hierarchy(
        session, foreign_version_scope
    )
    session.close()


def _valid_education_metadata() -> dict:
    return {
        "difficulty_evidence": {
            "cognitive_demand_band": 2,
            "step_count": 1,
            "computation_load": 2,
            "language_load": 1,
        },
        "cognitive_demand_evidence": {"application_required": True},
        "age_min": 12,
        "age_max": 14,
        "synthetic_fixture": True,
    }


def test_hitl_edit_can_revalidate_to_pass() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-edit-pass"
    )
    paused = service.run(request)
    item_id = paused.metadata_json["interrupt_payload"]["item_ids"][0]
    completed = service.run(
        request,
        resume=HumanResumeDecision(
            action="edit",
            item_patches={item_id: {"metadata_json": _valid_education_metadata()}},
        ),
    )
    assert completed.status == OrchestrationRunStatus.COMPLETED
    service.close()
    session.close()


def test_hitl_edit_can_pause_again_then_accept_second_decision() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-edit-second"
    )
    paused = service.run(request)
    item_id = paused.metadata_json["interrupt_payload"]["item_ids"][0]
    paused_again = service.run(
        request,
        resume=HumanResumeDecision(
            action="edit",
            item_patches={item_id: {"stem_text": "Synthetic edited stem"}},
        ),
    )
    assert paused_again.status == OrchestrationRunStatus.REVIEW_REQUIRED
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED
    service.close()
    session.close()


def test_invalid_resume_payload_is_structured_failure() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-invalid-resume"
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    failed = service.run(request, resume={"action": "not-valid"})
    assert failed.status == OrchestrationRunStatus.FAILED
    assert "invalid_human_resume" in failed.errors
    service.close()
    session.close()


def test_human_cannot_rewrite_provenance_controls() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="hitl-provenance-guard"
    )
    paused = service.run(request)
    item_id = paused.metadata_json["interrupt_payload"]["item_ids"][0]
    failed = service.run(
        request,
        resume=HumanResumeDecision(
            action="edit",
            item_patches={item_id: {"source_revision_ids": ["foreign-revision"]}},
        ),
    )
    assert failed.status == OrchestrationRunStatus.FAILED
    assert "human_edit_provenance_forbidden" in failed.errors
    service.close()
    session.close()


class _WrongReviewerGateway(FakeGenerationGateway):
    def generate(self, request: GenerationRequest):
        response = super().generate(request)
        if request.role == GenerationNodeRole.PATTERN_REVIEW:
            parsed = dict(response.parsed)
            parsed["reviewer"] = GenerationNodeRole.EDUCATIONAL_REVIEW.value
            return response.__class__(
                parsed=parsed,
                raw_text=response.raw_text,
                latency_ms=response.latency_ms,
                gateway_request_id=response.gateway_request_id,
                usage=response.usage,
                call_context=response.call_context,
            )
        return response


def test_reviewer_identity_and_cardinality_fail_closed() -> None:
    session = _session()
    gateway = _WrongReviewerGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_orchestration_request(ctx, idempotency_key="wrong-reviewer-role")
    )
    assert result.status == OrchestrationRunStatus.FAILED
    assert "model_reviewer_identity_mismatch" in result.errors
    service.close()
    session.close()


def test_day7_service_failure_is_structured_end_to_end() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic Day 7 failure")

    service.dependencies.knowledge_service.retrieve = _boom  # type: ignore[method-assign]
    result = service.run(
        build_orchestration_request(ctx, idempotency_key="day7-service-failure")
    )
    assert result.status == OrchestrationRunStatus.FAILED
    assert "day7_service_error" in result.errors
    service.close()
    session.close()


class _CrashOnSecondAuthorGateway(FakeGenerationGateway):
    def __init__(self) -> None:
        super().__init__()
        self.author_calls = 0

    def generate(self, request: GenerationRequest):
        if request.role == GenerationNodeRole.AUTHOR:
            self.author_calls += 1
            if self.author_calls == 2:
                raise SystemExit("synthetic crash between model calls")
        response = super().generate(request)
        if request.role != GenerationNodeRole.AUTHOR:
            return response
        parsed = dict(response.parsed)
        parsed["stem_text"] = (
            f"{parsed['stem_text']} [{request.user_payload.get('item_id', 'item')}]"
        )
        return response.__class__(
            parsed=parsed,
            raw_text=response.raw_text,
            latency_ms=response.latency_ms,
            gateway_request_id=response.gateway_request_id,
            usage=response.usage,
            call_context=response.call_context,
        )


def test_multicall_crash_restart_reuses_completed_call(tmp_path: Path) -> None:
    db_path = tmp_path / "day8-restart.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    ki = FakeAnythingLLMAdapter()
    with Session(engine) as session:
        ctx = seed_day8_fixtures(session, adapter=ki)
        check_a = build_managed_checkpointer(Settings(database_url=url))
        crash_gateway = _CrashOnSecondAuthorGateway()
        service_a = build_orchestration_service(
            session,
            gateway=crash_gateway,
            knowledge_adapter=ki,
            checkpointer=check_a,
            force_fake=False,
        )
        request = build_orchestration_request(
            ctx,
            requested_count=2,
            idempotency_key="multi-call-crash-restart",
        )
        with pytest.raises(SystemExit):
            service_a.run(request)
        service_a.close()

        check_b = build_managed_checkpointer(Settings(database_url=url))
        gateway_b = FakeGenerationGateway()
        service_b = build_orchestration_service(
            session,
            gateway=gateway_b,
            knowledge_adapter=ki,
            checkpointer=check_b,
            force_fake=False,
        )
        result = service_b.run(request, allow_gateway_retry=True)
        fresh_author_calls = [
            call
            for call in gateway_b.call_history()
            if call.call_context is not None
            and call.call_context.role == GenerationNodeRole.AUTHOR
        ]
        restart_snapshot = service_b.compiled_graph.get_state(
            {"configurable": {"thread_id": result.run_id}}
        )
        assert result.status == OrchestrationRunStatus.COMPLETED, {
            "errors": result.errors,
            "metadata": result.metadata_json,
            "snapshot_next": restart_snapshot.next,
            "snapshot_status": restart_snapshot.values.get("status"),
            "snapshot_errors": restart_snapshot.values.get("errors"),
            "gateway_retry_node": restart_snapshot.values.get("gateway_retry_node"),
        }
        assert len(fresh_author_calls) == 1
        assert fresh_author_calls[0].call_context is not None
        assert fresh_author_calls[0].call_context.item_id.endswith("-slot-1")
        service_b.close()


def test_real_candidate_sha_gate_match_mismatch_and_unknown(monkeypatch) -> None:
    from app import day8_verify

    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", "same")
    monkeypatch.setattr(day8_verify, "_git_head", lambda: "same")
    _, _, matched = day8_verify._candidate_sha_checks()
    assert matched == {
        "candidate_sha_resolved": True,
        "candidate_sha_matches_head": True,
    }

    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", "candidate")
    monkeypatch.setattr(day8_verify, "_git_head", lambda: "head")
    _, _, mismatched = day8_verify._candidate_sha_checks()
    assert mismatched["candidate_sha_matches_head"] is False

    monkeypatch.delenv("EDUVIJNA_CANDIDATE_SHA", raising=False)
    monkeypatch.setattr(day8_verify, "_git_head", lambda: "unknown")
    _, _, unknown = day8_verify._candidate_sha_checks()
    assert unknown["candidate_sha_resolved"] is False


def test_founder_verifier_exercises_end_to_end_tenant_isolation(monkeypatch) -> None:
    from app import day8_verify

    monkeypatch.setenv("EDUVIJNA_CANDIDATE_SHA", "same")
    monkeypatch.setattr(day8_verify, "_git_head", lambda: "same")
    session = _session()
    report = day8_verify.build_verification_report(session)
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert checks["foreign_tenant_scope_enforced"] is True
    assert checks["candidate_sha_matches_head"] is True
    session.close()
