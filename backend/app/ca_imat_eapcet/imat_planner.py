from __future__ import annotations

from decimal import Decimal

from app.ca_imat_eapcet.constants import IMAT_PACK_CODE, IMAT_TOTAL_QUESTIONS
from app.ca_imat_eapcet.contracts import AllocateRequest, ImatPaperPlanRequest, ImatPaperPlanResult
from app.ca_imat_eapcet.enums import Day14SourceTrustMode, IssueCode, PlanVerdict
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.scoring import score_imat_decimal
from app.ca_imat_eapcet.synthetic_fixtures import build_imat_pool


class ImatPaperPlanner:
    """D14-16..20: IMAT profile with decimal scoring and section allocation."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: ImatPaperPlanRequest) -> ImatPaperPlanResult:
        target = request.requested_count or IMAT_TOTAL_QUESTIONS
        alloc = self._practice.allocate(
            AllocateRequest(
                exam_pack_code=IMAT_PACK_CODE,
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                paper_or_section="full_paper",
                requested_count=target,
                academic_year=request.academic_year,
            )
        )

        sections: dict[str, int] = {}
        for q in alloc.questions:
            sections[q.paper_or_section] = sections.get(q.paper_or_section, 0) + 1

        decimal_total = Decimal("0")
        for _ in alloc.questions:
            decimal_total += score_imat_decimal(correct=True, answered=True)

        verdict = alloc.verdict
        if target == IMAT_TOTAL_QUESTIONS and alloc.delivered_count != IMAT_TOTAL_QUESTIONS:
            verdict = PlanVerdict.SHORTAGE
            alloc.issue_codes.append(IssueCode.IMAT_COUNT_MISMATCH)

        if len(build_imat_pool()) != IMAT_TOTAL_QUESTIONS:
            verdict = PlanVerdict.FAIL

        return ImatPaperPlanResult(
            verdict=verdict,
            total_questions=target,
            delivered_count=alloc.delivered_count,
            sections=sections,
            decimal_total_marks=float(decimal_total.quantize(Decimal("0.1"))),
            issue_codes=alloc.issue_codes,
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "options_per_question": 5,
            },
        )