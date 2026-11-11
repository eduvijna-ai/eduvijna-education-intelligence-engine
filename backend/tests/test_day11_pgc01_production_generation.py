from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.common.trust_execution import TrustExecutionMode
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import JEE_MAIN_VERSION_2027
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.exam_catalogue import ensure_jee_main_exam_catalogue
from app.jee_main_exam_intelligence.generation import assemble_paper_with_persistence
from app.jee_main_exam_intelligence.orchestration_bridge import (
    _INJECT_CHECKPOINT_KEY,
    _INJECT_KI_KEY,
    acquire_orchestration_service,
    build_jee_production_orchestration_request,
    persist_draft_items_as_jee_questions,
)
from app.jee_main_exam_intelligence.source_authority import register_nta_2027_candidate_sources
from app.models.enums import QuestionStatus
from app.models.question import Question
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import seed_day8_fixtures
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from tests.day10_day6_binding import seed_production_day6_audit


def _file_session(db_path: Path) -> tuple[Session, str]:
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine), url


def _four_options(correct: str = "B") -> list[QuestionOptionDraft]:
    keys = ("A", "B", "C", "D")
    return [
        QuestionOptionDraft(
            option_key=key,
            text=f"value-{key}",
            is_correct=key == correct,
        )
        for key in keys
    ]


def test_production_factory_uses_live_adapter_factories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc-factory.db"
        session, url = _file_session(db)
        gateway = FakeGenerationGateway()
        ki = FakeAnythingLLMAdapter()
        session.info[_INJECT_KI_KEY] = ki
        session.info[_INJECT_CHECKPOINT_KEY] = build_managed_checkpointer(
            Settings(database_url=url), memory_only=False
        )
        ctx = seed_day8_fixtures(session, adapter=ki)
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="pgc-factory",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            topic_code="sets-relations-functions",
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={
                "orchestration_scope": {
                    **ctx,
                    "exam_version_id": "ev-1",
                    "grade_year_code": "grade-8",
                    "medium_code": "english",
                }
            },
        )
        with (
            mock.patch(
                "app.jee_main_exam_intelligence.orchestration_bridge.build_day8_test_service"
            ) as fixture_builder,
            mock.patch(
                "app.jee_main_exam_intelligence.orchestration_bridge.build_anythingllm_adapter"
            ) as ki_factory,
        ):
            ki_factory.side_effect = AssertionError("production must use injected KI adapter")
            _, service = acquire_orchestration_service(session, req, gateway)
            fixture_builder.assert_not_called()
            service.close()
        session.close()


def test_production_orchestration_request_has_no_fixture_scenario() -> None:
    scope = {
        "curriculum_version_id": "cv1",
        "learning_outcome_id": "lo1",
        "organization_id": "org1",
        "institution_id": "inst1",
        "official_revision_id": "rev1",
        "grade_year_code": "grade-8",
        "medium_code": "english",
    }
    req = PaperPlanRequest(
        plan_id="pgc-scope",
        exam_version_code=JEE_MAIN_VERSION_2027,
        mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
        organization_id="org1",
        institution_id="inst1",
        subject_code=JeeMainSubjectCode.MATHEMATICS,
        topic_code="sets-relations-functions",
        requested_count=1,
        execution_mode=TrustExecutionMode.PRODUCTION,
    )
    orch = build_jee_production_orchestration_request(
        req, scope, shortage=1, idempotency_key="pgc-scope-key99"
    )
    assert "fixture_scenario" not in orch.metadata_json
    assert orch.grade_year_code == "grade-8"
    assert orch.subject_code == "mathematics"
    assert "sets-relations-functions" in orch.topic_codes


def test_production_persist_rejects_solver_disagree_mcq() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc-solver.db"
        session, _ = _file_session(db)
        ctx = seed_day8_fixtures(session)
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        org = ctx["organization_id"]
        run_id, validated = seed_production_day6_audit(
            session,
            item_id="pgc-solver-item",
            organization_id=org,
            institution_id=ctx["institution_id"],
        )
        session.commit()
        request = PaperPlanRequest(
            plan_id="solver-disagree",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=org,
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            topic_code="sets-relations-functions",
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
        )
        draft = DraftQuestionItem(
            item_id="pgc-solver-item",
            slot_index=0,
            stem_text="What is 7+5?",
            options=_four_options("B"),
            source_revision_ids=[ctx["official_revision_id"]],
            metadata_json={
                "official_topic_codes": ["sets-relations-functions"],
                "solver_proposed_answer_key": "A",
                "day6_validation_run_id": run_id,
                "day6_input_hash": validated["input_hash"],
            },
        )
        created, issues = persist_draft_items_as_jee_questions(
            session,
            items=[draft],
            request=request,
            source_revision_ids=[ctx["official_revision_id"]],
        )
        assert not created
        assert PaperPlanIssueCode.INVALID_ANSWER in issues


def test_production_file_db_orchestration_one_item_day6() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc-live.db"
        session, url = _file_session(db)
        gateway = FakeGenerationGateway()
        ki = FakeAnythingLLMAdapter()
        session.info[_INJECT_KI_KEY] = ki
        session.info[_INJECT_CHECKPOINT_KEY] = build_managed_checkpointer(
            Settings(database_url=url), memory_only=False
        )
        ctx = seed_day8_fixtures(session, adapter=ki)
        register_nta_2027_candidate_sources(session)
        catalogue = ensure_jee_main_exam_catalogue(session)
        ctx["exam_version_id"] = catalogue["versions"][JEE_MAIN_VERSION_2027]
        session.commit()
        req = PaperPlanRequest(
            plan_id="pgc-live-one",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            idempotency_key="pgc-live-one-key",
            metadata_json={
                "require_live_generation": True,
                "orchestration_scope": {
                    **ctx,
                    "grade_year_code": "grade-8",
                    "medium_code": "english",
                },
                "enforce_paper_distribution": False,
                "retrieval_query": "quadratic equations completing square",
                "test_injected_generation_scenario": "clean_pass",
            },
        )
        with mock.patch(
            "app.jee_main_exam_intelligence.orchestration_bridge.build_day8_test_service"
        ) as fixture_builder:
            result = assemble_paper_with_persistence(
                session, req, gateway=gateway, persist=False
            )
            fixture_builder.assert_not_called()
        session.commit()
        generated = [
            q
            for q in session.scalars(select(Question)).all()
            if (q.metadata_json or {}).get("orchestration_origin")
        ]
        if result.verdict == PaperPlanVerdict.PASS:
            assert len(generated) == 1
            assert generated[0].status == QuestionStatus.APPROVED.value
            assert generated[0].metadata_json.get("day6_validation_run_id")
        else:
            assert not generated or PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL in (
                result.issue_codes
            )


def test_durable_hitl_resume_no_duplicate_author_gateway_calls() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc-hitl.db"
        session, url = _file_session(db)
        gateway = FakeGenerationGateway()
        ki = FakeAnythingLLMAdapter()
        managed = build_managed_checkpointer(Settings(database_url=url), memory_only=False)
        ctx = seed_day8_fixtures(session, adapter=ki)
        scoped = {**ctx, "grade_year_code": "grade-8", "medium_code": "english"}
        session.commit()
        service_a = build_orchestration_service(
            session,
            gateway=gateway,
            knowledge_adapter=ki,
            checkpointer=managed,
            force_fake=True,
        )
        request = PaperPlanRequest(
            plan_id="hitl-durable",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={
                "orchestration_scope": scoped,
                "test_injected_generation_scenario": "human_review",
                "retrieval_query": "quadratic equations completing square",
            },
        )
        orch = build_jee_production_orchestration_request(
            request,
            scoped,
            shortage=1,
            idempotency_key="pgc-durable-hitl-key",
        )
        orch = orch.model_copy(
            update={
                "metadata_json": {
                    **orch.metadata_json,
                    "deterministic_human_review_required": True,
                }
            }
        )
        paused = service_a.run(orch)
        assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED, paused.errors
        calls_at_pause = len(gateway.call_history())

        factory = sessionmaker(bind=session.get_bind())
        with factory() as session_b:
            service_b = build_orchestration_service(
                session_b,
                gateway=gateway,
                knowledge_adapter=ki,
                checkpointer=managed,
                force_fake=True,
            )
            completed = service_b.run(
                orch, resume=HumanResumeDecision(action="approve")
            )
            calls_after_resume = len(gateway.call_history())
        assert completed.status == OrchestrationRunStatus.COMPLETED
        assert calls_after_resume == calls_at_pause
        service_a.close()
        managed.close()
