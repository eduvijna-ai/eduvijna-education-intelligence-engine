from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.fixtures import (
    build_practice_math_ten_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.generation import assemble_paper_with_persistence
from app.jee_main_exam_intelligence.persistence import persistence_definition_code
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption
from app.models.question import TestDefinition as PersistedTestDefinition
from app.orchestration.gateway.fake import FakeGenerationGateway
from tests.day10_day6_binding import seed_production_day6_audit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_foreign_pool_row_does_not_veto_own_tenant_synthetic_pool() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.add(
            Question(
                external_code="foreign-row",
                origin_type="teacher",
                question_type=QuestionType.MULTIPLE_CHOICE.value,
                stem_text="foreign",
                answer_json={"correct_option": "A"},
                status=QuestionStatus.APPROVED.value,
                metadata_json={
                    "jee_main_subject_code": "mathematics",
                    "organization_id": "tenant-foreign",
                    "synthetic_fixture": True,
                    "jee_main_trust_harness_token": "wrong-token",
                },
            )
        )
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(session, build_practice_math_ten_request(ctx), persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
        assert PaperPlanIssueCode.FOREIGN_TENANT_CONTENT not in result.issue_codes


def test_cognitive_distribution_pass_on_synthetic_ten() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={
                "metadata_json": {
                    "evaluate_paper_distribution": True,
                    "cognitive_targets": [
                        {
                            "dimension": "cognitive",
                            "key": "apply",
                            "exact_percent": 100.0,
                        }
                    ],
                }
            }
        )
        result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.metadata_json.get("paper_distribution", {}).get("verdict") == "pass"


def test_cognitive_distribution_violation_typed_fail() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={
                "metadata_json": {
                    "evaluate_paper_distribution": True,
                    "cognitive_targets": [
                        {
                            "dimension": "cognitive",
                            "key": "remember",
                            "exact_percent": 100.0,
                        }
                    ],
                }
            }
        )
        result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.COGNITIVE_DISTRIBUTION_VIOLATION in result.issue_codes


def test_persistence_scoped_codes_per_tenant() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        req_a = build_practice_math_ten_request(ctx).model_copy(update={"plan_id": "shared-plan"})
        req_b = build_practice_math_ten_request(ctx).model_copy(
            update={"plan_id": "shared-plan", "organization_id": "tenant-b"}
        )
        res_a = service.plan_paper(session, req_a)
        res_b = service.plan_paper(session, req_b)
        assert res_a.test_definition_id != res_b.test_definition_id
        codes = session.scalars(select(PersistedTestDefinition.code)).all()
        assert len(codes) == 2
        assert persistence_definition_code(req_a) != persistence_definition_code(req_b)


def test_persistence_idempotency_replay_and_conflict() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        base = build_practice_math_ten_request(ctx).model_copy(
            update={"plan_id": "idem-plan", "idempotency_key": "idem-stable"}
        )
        first = service.plan_paper(session, base)
        assert first.verdict == PaperPlanVerdict.PASS
        second = service.plan_paper(session, base)
        assert second.verdict == PaperPlanVerdict.PASS
        assert second.test_definition_id == first.test_definition_id

        conflict = service.plan_paper(
            session,
            base.model_copy(
                update={
                    "derived_topic_group": "algebra",
                    "plan_id": "idem-plan",
                }
            ),
        )
        assert conflict.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT in conflict.issue_codes


def test_live_generation_boundary_uses_pool_without_gateway() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"metadata_json": {"require_live_generation": True}}
        )
        result = assemble_paper_with_persistence(session, req, gateway=None, persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.metadata_json.get("generation_path") == "validated_question_pool"
        assert result.metadata_json.get("gateway_invoked") is False


def test_live_generation_boundary_pool_path_with_gateway() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"metadata_json": {"require_live_generation": True}}
        )
        result = assemble_paper_with_persistence(
            session, req, gateway=FakeGenerationGateway(), persist=False
        )
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.metadata_json.get("generation_path") == "validated_question_pool"
        assert result.metadata_json.get("gateway_invoked") is False


def test_production_practice_ten_with_persisted_day6_binding() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        org = ctx["organization_id"]
        inst = ctx["institution_id"]
        curriculum_version_id = None
        for index in range(10):
            item_id = f"d11-prod-math-{index:02d}"
            run_id, validated = seed_production_day6_audit(
                session,
                item_id=item_id,
                organization_id=org,
                institution_id=inst,
                curriculum_version_id=curriculum_version_id,
                declared_cognitive_level="apply",
            )
            question = Question(
                external_code=item_id,
                origin_type="teacher",
                question_type=QuestionType.MULTIPLE_CHOICE.value,
                stem_text=f"Production item {index}",
                answer_json={"correct_option": "A"},
                status=QuestionStatus.APPROVED.value,
                metadata_json={
                    "jee_main_subject_code": "mathematics",
                    "organization_id": org,
                    "institution_id": inst,
                    "exam_version_id": ctx["exam_version_2027_id"],
                    "official_topic_codes": ["sets-relations-functions"],
                    "day6_validation_run_id": run_id,
                    "day6_input_hash": validated["input_hash"],
                    "learning_outcome_ids": validated["learning_outcome_ids"],
                    "competency_codes": validated["competency_codes"],
                    "cognitive_level": "apply",
                    "curriculum_version_id": validated.get("curriculum_version_id"),
                },
            )
            session.add(question)
            session.flush()
            for key in ("A", "B", "C", "D"):
                session.add(
                    QuestionOption(
                        question_id=question.id,
                        option_key=key,
                        text=f"opt {key}",
                        is_correct=key == "A",
                    )
                )
        session.commit()
        req = PaperPlanRequest(
            plan_id="prod-math-10",
            exam_version_code="2027",
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=org,
            institution_id=inst,
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            requested_count=10,
            execution_mode=TrustExecutionMode.PRODUCTION,
        )
        result = JeeMainExamIntelligenceService().plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
