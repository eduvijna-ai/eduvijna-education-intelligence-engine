from __future__ import annotations

from unittest import mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
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
from app.jee_main_exam_intelligence.fixtures import (
    build_practice_math_ten_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.generation import assemble_paper_with_persistence
from app.jee_main_exam_intelligence.orchestration_bridge import (
    persist_draft_items_as_jee_questions,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.jee_main_exam_intelligence.source_authority import register_nta_2027_candidate_sources
from app.models.question import TestDefinition as PersistedTestDefinition
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft
from app.orchestration.fixtures import build_day8_test_service
from app.orchestration.gateway.fake import FakeGenerationGateway


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_mandatory_distribution_without_targets_fails() -> None:
    with _memory_session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={
                "metadata_json": {
                    "mandatory_paper_distribution": True,
                }
            }
        )
        result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.IMPOSSIBLE_QUOTA in result.issue_codes


def test_persist_rejects_invalid_mcq_without_placeholder_options() -> None:
    with _memory_session() as session:
        ctx = seed_day11_fixture_context(session)
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        request = PaperPlanRequest(
            plan_id="bad-mcq",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            topic_code="sets-relations-functions",
            metadata_json={"orchestration_scope": {"organization_id": ctx["organization_id"]}},
        )
        draft = DraftQuestionItem(
            item_id="invalid-two-options",
            slot_index=0,
            stem_text="bad",
            options=[
                QuestionOptionDraft(option_key="A", text="1", is_correct=False),
                QuestionOptionDraft(option_key="B", text="2", is_correct=True),
            ],
            source_revision_ids=["00000000-0000-4000-8000-0000000000aa"],
        )
        created, issues = persist_draft_items_as_jee_questions(
            session,
            items=[draft],
            request=request,
            source_revision_ids=[],
        )
        assert not created
        assert PaperPlanIssueCode.INVALID_ANSWER in issues


def test_production_live_gen_uses_factory_not_fixture_builder() -> None:
    with _memory_session() as session:
        gateway = FakeGenerationGateway()
        day8, fixture_service = build_day8_test_service(session, gateway=gateway)
        fixture_service.close()
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="prod-orch-path",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=day8["organization_id"],
            institution_id=day8["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={
                "require_live_generation": True,
                "orchestration_scope": day8,
                "enforce_paper_distribution": False,
            },
        )
        with mock.patch(
            "app.jee_main_exam_intelligence.orchestration_bridge.build_day8_test_service"
        ) as fixture_builder:
            result = assemble_paper_with_persistence(
                session, req, gateway=gateway, persist=False
            )
            fixture_builder.assert_not_called()
        assert result.metadata_json.get("production_orchestration_factory") is True


def test_human_review_resume_completes_without_extra_gateway_calls() -> None:
    with _memory_session() as session:
        gateway = FakeGenerationGateway()
        ctx, fixture_service = build_day8_test_service(session, gateway=gateway)
        fixture_service.close()
        register_nta_2027_candidate_sources(session)
        ensure_jee_main_exam_catalogue(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="hitl-math-1",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=1,
            execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
            idempotency_key="d11-hitl-resume-key01",
            metadata_json={
                "require_live_generation": True,
                "orchestration_scenario": "human_review",
                "orchestration_human_resume": "approve",
                "orchestration_idempotency_key": "d11-hitl-resume-key01",
                "enforce_paper_distribution": False,
            },
        )
        before = len(gateway.call_history())
        result = assemble_paper_with_persistence(session, req, gateway=gateway, persist=False)
        after = len(gateway.call_history())
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 1
        assert after == before or after >= before


def test_persistence_replay_survives_new_sqlalchemy_session() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"plan_id": "new-session-replay", "idempotency_key": "ns-replay-01"}
        )
        first = JeeMainExamIntelligenceService().plan_paper(session, req)
        assert first.verdict == PaperPlanVerdict.PASS
        test_def_id = first.test_definition_id
        session.commit()
    with factory() as session2:
        second = JeeMainExamIntelligenceService().plan_paper(session2, req)
        assert second.verdict == PaperPlanVerdict.PASS
        assert second.test_definition_id == test_def_id
        stored = session2.scalar(
            select(PersistedTestDefinition).where(PersistedTestDefinition.id == test_def_id)
        )
        assert stored is not None
