from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine
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
from app.jee_main_exam_intelligence.generation import (
    _INJECT_GATEWAY_KEY,
    resolve_live_generation_gateway,
)
from app.jee_main_exam_intelligence.orchestration_bridge import (
    _INJECT_CHECKPOINT_KEY,
    _INJECT_KI_KEY,
    build_jee_production_orchestration_request,
    persist_draft_items_as_jee_questions,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.jee_main_exam_intelligence.source_authority import register_nta_2027_candidate_sources
from app.models.enums import QuestionStatus
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.exceptions import OrchestrationConfigurationError
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
    return [
        QuestionOptionDraft(
            option_key=key,
            text={"A": "11", "B": "12", "C": "13", "D": "14"}[key],
            is_correct=key == correct,
        )
        for key in ("A", "B", "C", "D")
    ]


def _production_trust(
    item_id: str,
    *,
    run_id: str,
    input_hash: str,
    solver_key: str = "B",
    agrees: bool = True,
) -> dict[str, dict[str, object]]:
    return {
        item_id: {
            "deterministic": {
                "item_id": item_id,
                "blocking": False,
                "repairable": False,
                "review_required": False,
                "issue_codes": [],
                "day6_validation_run_id": run_id,
                "input_hash": input_hash,
                "learning_outcome_ids": ["00000000-0000-4000-8000-0000000000d6"],
                "competency_codes": ["knowledge"],
                "day6_content_fingerprint": input_hash,
            },
            "solver": {
                "item_id": item_id,
                "proposed_answer_key": solver_key,
                "check_status": "ok",
                "agrees_with_author": agrees,
            },
        }
    }


def test_plan_paper_resolves_gateway_without_explicit_arg() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc02-service.db"
        session, url = _file_session(db)
        gateway = FakeGenerationGateway()
        ki = FakeAnythingLLMAdapter()
        session.info[_INJECT_GATEWAY_KEY] = gateway
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
            plan_id="pgc02-normal-service",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            idempotency_key="pgc02-normal-service-key",
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
            result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
            fixture_builder.assert_not_called()
        assert resolve_live_generation_gateway(session, req, None) is gateway
        if result.verdict == PaperPlanVerdict.PASS:
            assert result.actual_count == 1
            assert result.metadata_json.get("gateway_invoked") is True
        else:
            assert PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL in result.issue_codes


def test_production_missing_gateway_config_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc02-no-creds.db"
        session, _ = _file_session(db)
        ctx = seed_day8_fixtures(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="pgc02-no-creds",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={
                "require_live_generation": True,
                "orchestration_scope": {
                    **ctx,
                    "grade_year_code": "grade-8",
                    "medium_code": "english",
                },
            },
        )
        with mock.patch(
            "app.jee_main_exam_intelligence.generation.build_generation_gateway",
            side_effect=OrchestrationConfigurationError("missing"),
        ):
            result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.LIVE_GENERATION_NOT_CONFIGURED in result.issue_codes


def test_production_persist_rejects_missing_solver_trust() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc02-miss-solver.db"
        session, _ = _file_session(db)
        ctx = seed_day8_fixtures(session)
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        org = ctx["organization_id"]
        item_id = "pgc02-no-solver"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=org,
            institution_id=ctx["institution_id"],
            curriculum_version_id=ctx["curriculum_version_id"],
        )
        session.commit()
        request = PaperPlanRequest(
            plan_id="pgc02-miss-solver",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=org,
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            topic_code="sets-relations-functions",
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={"curriculum_version_id": ctx["curriculum_version_id"]},
        )
        draft = DraftQuestionItem(
            item_id=item_id,
            slot_index=0,
            stem_text="What is 7+5?",
            options=_four_options("B"),
            source_revision_ids=[ctx["official_revision_id"]],
            metadata_json={"official_topic_codes": ["sets-relations-functions"]},
        )
        created, issues = persist_draft_items_as_jee_questions(
            session,
            items=[draft],
            request=request,
            source_revision_ids=[ctx["official_revision_id"]],
            orchestration_trust=None,
        )
        assert not created
        assert PaperPlanIssueCode.INVALID_ANSWER in issues

        created2, issues2 = persist_draft_items_as_jee_questions(
            session,
            items=[draft],
            request=request,
            source_revision_ids=[ctx["official_revision_id"]],
            orchestration_trust=_production_trust(
                item_id,
                run_id=run_id,
                input_hash=str(validated["input_hash"]),
                solver_key="A",
                agrees=False,
            ),
        )
        assert not created2
        assert PaperPlanIssueCode.INVALID_ANSWER in issues2


def test_production_persist_accepts_independent_solver_trust() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc02-solver-ok.db"
        session, _ = _file_session(db)
        ctx = seed_day8_fixtures(session)
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        org = ctx["organization_id"]
        item_id = "pgc02-solver-ok"
        run_id, validated = seed_production_day6_audit(
            session,
            item_id=item_id,
            organization_id=org,
            institution_id=ctx["institution_id"],
            curriculum_version_id=ctx["curriculum_version_id"],
        )
        session.commit()
        request = PaperPlanRequest(
            plan_id="pgc02-solver-ok",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=org,
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            topic_code="sets-relations-functions",
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={"curriculum_version_id": ctx["curriculum_version_id"]},
        )
        draft = DraftQuestionItem(
            item_id=item_id,
            slot_index=0,
            stem_text="What is 7+5?",
            options=_four_options("B"),
            source_revision_ids=[ctx["official_revision_id"]],
            metadata_json={"official_topic_codes": ["sets-relations-functions"]},
        )
        created, issues = persist_draft_items_as_jee_questions(
            session,
            items=[draft],
            request=request,
            source_revision_ids=[ctx["official_revision_id"]],
            orchestration_trust=_production_trust(
                item_id,
                run_id=run_id,
                input_hash=str(validated["input_hash"]),
            ),
        )
        assert not issues
        assert len(created) == 1
        assert created[0].status == QuestionStatus.APPROVED.value


def test_durable_hitl_reopens_checkpointer_after_close() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pgc02-hitl.db"
        session, url = _file_session(db)
        gateway = FakeGenerationGateway()
        ki = FakeAnythingLLMAdapter()
        ctx = seed_day8_fixtures(session, adapter=ki)
        scoped = {**ctx, "grade_year_code": "grade-8", "medium_code": "english"}
        session.commit()
        settings = Settings(database_url=url)
        managed_a = build_managed_checkpointer(settings, memory_only=False)
        service_a = build_orchestration_service(
            session,
            gateway=gateway,
            knowledge_adapter=ki,
            checkpointer=managed_a,
            force_fake=True,
        )
        request = PaperPlanRequest(
            plan_id="hitl-pgc02",
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
            idempotency_key="pgc02-durable-hitl-key",
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
        paused_run_id = paused.run_id
        service_a.close()
        managed_a.close()
        session.close()

        engine = create_engine(f"sqlite:///{db}")
        enable_sqlite_foreign_keys(engine)
        factory = sessionmaker(bind=engine)
        with factory() as session_b:
            managed_b = build_managed_checkpointer(settings, memory_only=False)
            service_b = build_orchestration_service(
                session_b,
                gateway=gateway,
                knowledge_adapter=ki,
                checkpointer=managed_b,
                force_fake=True,
            )
            completed = service_b.run(
                orch, resume=HumanResumeDecision(action="approve")
            )
            calls_after_resume = len(gateway.call_history())
            service_b.close()
            managed_b.close()
        assert completed.status == OrchestrationRunStatus.COMPLETED
        assert completed.run_id == paused_run_id
        assert calls_after_resume == calls_at_pause
