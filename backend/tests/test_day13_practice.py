from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE, MATHEMATICS_DOMAIN
from app.cuet_clat.contracts import ClatPaperPlanRequest, CuetPracticeRequest, CuetSingleTestRequest
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, PlanVerdict
from app.cuet_clat.practice_service import CuetPracticeService


def test_cuet_math_10_exact_synthetic() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(
        CuetPracticeRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
            requested_count=10,
        )
    )
    assert result.verdict == PlanVerdict.PASS
    assert result.delivered_count == 10


def test_cuet_single_test_50_synthetic() -> None:
    svc = CuetPracticeService()
    result = svc.assemble_single_test(
        CuetSingleTestRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
        )
    )
    assert result.verdict == PlanVerdict.PASS
    assert result.question_count == 50
    assert result.marks_correct == 5.0
    assert result.marks_incorrect == -1.0


def test_clat_120_with_passage_clusters() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        )
    )
    assert plan.verdict == PlanVerdict.PASS
    assert plan.total_questions == 120
    assert len(plan.passage_clusters) >= 5
    assert sum(a.question_count for a in plan.section_allocations) == 120