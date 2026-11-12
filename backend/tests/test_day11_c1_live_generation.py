from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import DERIVED_TOPIC_ALGEBRA, JEE_MAIN_VERSION_2027
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.exam_catalogue import ensure_jee_main_exam_catalogue
from app.jee_main_exam_intelligence.generation import assemble_paper_with_persistence
from app.jee_main_exam_intelligence.source_authority import register_nta_2027_candidate_sources
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption
from app.orchestration.fixtures import build_day8_test_service
from app.orchestration.gateway.fake import FakeGenerationGateway
from tests.day10_day6_binding import seed_production_day6_audit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _ctx_without_pool(session: Session) -> tuple[dict[str, str], FakeGenerationGateway]:
    gateway = FakeGenerationGateway()
    day8, _service = build_day8_test_service(session, gateway=gateway)
    _service.close()
    register_nta_2027_candidate_sources(session)
    catalogue = ensure_jee_main_exam_catalogue(session)
    session.flush()
    return {
        "organization_id": day8["organization_id"],
        "institution_id": day8["institution_id"],
        "exam_version_2027_id": catalogue["versions"][JEE_MAIN_VERSION_2027],
    }, gateway


def test_live_generation_fills_empty_pool_ten_math() -> None:
    with _session() as session:
        ctx, gateway = _ctx_without_pool(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="live-math-10",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=10,
            execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
            idempotency_key="d11-live-math-10-key",
            metadata_json={
                "require_live_generation": True,
                "orchestration_scenario": "clean_pass",
                "enforce_paper_distribution": False,
            },
        )
        result = assemble_paper_with_persistence(
            session, req, gateway=gateway, persist=False
        )
        session.commit()
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
        assert result.metadata_json.get("generation_path") == "day8_orchestration"
        assert result.metadata_json.get("gateway_invoked") is True
        assert len(gateway.call_history()) >= 1


def test_live_generation_idempotent_replay_no_duplicate_gateway_work() -> None:
    with _session() as session:
        ctx, gateway = _ctx_without_pool(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="live-idem",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=3,
            execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
            idempotency_key="d11-live-idem-key99",
            metadata_json={
                "require_live_generation": True,
                "orchestration_idempotency_key": "d11-live-idem-key99",
                "enforce_paper_distribution": False,
            },
        )
        first = assemble_paper_with_persistence(session, req, gateway=gateway, persist=True)
        session.commit()
        calls_after_first = len(gateway.call_history())
        second = assemble_paper_with_persistence(session, req, gateway=gateway, persist=True)
        assert first.verdict == PaperPlanVerdict.PASS
        assert second.verdict == PaperPlanVerdict.PASS
        assert first.plan_checksum == second.plan_checksum
        assert second.metadata_json.get("generation_path") == "validated_question_pool"
        assert len(gateway.call_history()) == calls_after_first


def test_live_generation_repair_then_pass_scenario() -> None:
    with _session() as session:
        ctx, gateway = _ctx_without_pool(session)
        session.commit()
        req = PaperPlanRequest(
            plan_id="live-repair",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=2,
            execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
            idempotency_key="d11-live-repair-key",
            metadata_json={
                "require_live_generation": True,
                "orchestration_scenario": "repair_then_pass",
                "enforce_paper_distribution": False,
            },
        )
        result = assemble_paper_with_persistence(session, req, gateway=gateway, persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 2
        assert result.metadata_json.get("repair_summary")


def test_production_algebra_ten_with_day6_binding() -> None:
    with _session() as session:
        ctx, _gateway = _ctx_without_pool(session)
        org = ctx["organization_id"]
        inst = ctx["institution_id"]
        algebra_codes = ["complex-numbers-quadratic", "matrices-determinants"]
        for index in range(10):
            item_id = f"d11-prod-alg-{index:02d}"
            run_id, validated = seed_production_day6_audit(
                session,
                item_id=item_id,
                organization_id=org,
                institution_id=inst,
                declared_cognitive_level="apply",
            )
            question = Question(
                external_code=item_id,
                origin_type="teacher",
                question_type=QuestionType.MULTIPLE_CHOICE.value,
                stem_text=f"Algebra item {index}",
                answer_json={"correct_option": "A"},
                status=QuestionStatus.APPROVED.value,
                metadata_json={
                    "jee_main_subject_code": "mathematics",
                    "organization_id": org,
                    "institution_id": inst,
                    "exam_version_id": ctx["exam_version_2027_id"],
                    "official_topic_codes": algebra_codes,
                    "derived_topic_groups": [DERIVED_TOPIC_ALGEBRA],
                    "day6_validation_run_id": run_id,
                    "day6_input_hash": validated["input_hash"],
                    "learning_outcome_ids": validated["learning_outcome_ids"],
                    "competency_codes": validated["competency_codes"],
                    "cognitive_level": "apply",
                },
            )
            session.add(question)
            session.flush()
            for key in ("A", "B", "C", "D"):
                session.add(
                    QuestionOption(
                        question_id=question.id,
                        option_key=key,
                        text=key,
                        is_correct=key == "A",
                    )
                )
        session.commit()
        req = PaperPlanRequest(
            plan_id="prod-algebra-10",
            exam_version_code=JEE_MAIN_VERSION_2027,
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=org,
            institution_id=inst,
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            derived_topic_group=DERIVED_TOPIC_ALGEBRA,
            requested_count=10,
            execution_mode=TrustExecutionMode.PRODUCTION,
            metadata_json={"enforce_paper_distribution": False},
        )
        from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService

        result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
