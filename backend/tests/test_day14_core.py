from app.ca_imat_eapcet.ca_planner import CaFoundationPlanner
from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    EAPCET_PACK_CODE,
    EAPCET_TOTAL_QUESTIONS,
    IMAT_PACK_CODE,
    IMAT_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.contracts import (
    CaPaperPlanRequest,
    EapcetPaperPlanRequest,
    ImatPaperPlanRequest,
)
from app.ca_imat_eapcet.eapcet_planner import EapcetPaperPlanner
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    PlanVerdict,
)
from app.ca_imat_eapcet.imat_planner import ImatPaperPlanner


def test_ca_four_paper_synthetic_bundle() -> None:
    planner = CaFoundationPlanner()
    result = planner.plan(
        CaPaperPlanRequest(
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            items_per_paper=5,
        )
    )
    assert result.verdict == PlanVerdict.PASS
    assert len(result.papers) == 4
    assert result.total_marks > 0
    assert result.total_marks != 400


def test_imat_synthetic_full_paper() -> None:
    planner = ImatPaperPlanner()
    result = planner.plan(
        ImatPaperPlanRequest(
            exam_pack_code=IMAT_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
        )
    )
    assert result.verdict == PlanVerdict.PASS
    assert result.delivered_count == IMAT_TOTAL_QUESTIONS


def test_eapcet_engineering_160() -> None:
    planner = EapcetPaperPlanner()
    result = planner.plan(
        EapcetPaperPlanRequest(
            exam_pack_code=EAPCET_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            stream=EapcetStream.ENGINEERING,
        )
    )
    assert result.verdict == PlanVerdict.PASS
    assert result.delivered_count == EAPCET_TOTAL_QUESTIONS
    assert result.section_counts.get("mathematics") == 80


def test_wrong_pack_fail_closed() -> None:
    planner = ImatPaperPlanner()
    result = planner.plan(
        ImatPaperPlanRequest(
            exam_pack_code="wrong_pack",
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
        )
    )
    assert result.verdict == PlanVerdict.FAIL
    _ = CA_FOUNDATION_PACK_CODE