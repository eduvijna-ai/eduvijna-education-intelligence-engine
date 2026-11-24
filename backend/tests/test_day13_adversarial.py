from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.constants import (
    CLAT_PACK_CODE,
    CLAT_TOTAL_QUESTIONS,
    CUET_PACK_CODE,
    MATHEMATICS_DOMAIN,
)
from app.cuet_clat.contracts import ClatPaperPlanRequest, CuetPracticeRequest, CuetSingleTestRequest
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.practice_service import CuetPracticeService
from app.cuet_clat.section_allocator import allocate_clat_sections


def test_cuet_wrong_year_fail_closed() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(
        CuetPracticeRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.CUET_CANDIDATE_2027,
            trust_mode=CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED,
            test_subject_code=MATHEMATICS_DOMAIN,
            requested_count=10,
            academic_year="2027",
        )
    )
    assert result.verdict == PlanVerdict.OFFICIAL_NOT_VERIFIED


def test_cuet_count_49_rejected() -> None:
    svc = CuetPracticeService()
    result = svc.assemble_single_test(
        CuetSingleTestRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
            academic_year="2026",
            metadata_json={"forced_question_count": 49},
        )
    )
    assert result.verdict == PlanVerdict.FAIL
    assert IssueCode.CUET_COUNT_MISMATCH in result.issue_codes


def test_clat_count_119_rejected() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
            metadata_json={"forced_total_questions": 119},
        )
    )
    assert plan.verdict == PlanVerdict.FAIL


def test_clat_infeasible_section_override() -> None:
    outcome = allocate_clat_sections(
        section_overrides={
            "english": 26,
            "current_affairs_gk": 32,
            "legal_reasoning": 32,
            "logical_reasoning": 26,
            "quantitative_techniques": 14,
        }
    )
    assert outcome.verdict == PlanVerdict.FAIL
    assert IssueCode.CLAT_COUNT_MISMATCH in outcome.issue_codes


def test_clat_forced_citation_rejected() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
            metadata_json={"forged_citation": True},
        )
    )
    assert plan.verdict == PlanVerdict.FAIL
    assert IssueCode.FORGED_CITATION in plan.issue_codes


def test_clat_default_allocation_sums_120() -> None:
    outcome = allocate_clat_sections()
    assert outcome.verdict == PlanVerdict.PASS
    assert sum(outcome.allocations.values()) == CLAT_TOTAL_QUESTIONS