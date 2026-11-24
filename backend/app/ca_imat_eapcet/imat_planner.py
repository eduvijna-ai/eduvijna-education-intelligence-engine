from __future__ import annotations

from decimal import Decimal

from app.ca_imat_eapcet.constants import IMAT_TOTAL_QUESTIONS
from app.ca_imat_eapcet.contracts import AllocateRequest, ImatPaperPlanRequest, ImatPaperPlanResult
from app.ca_imat_eapcet.enums import Day14SourceTrustMode, IssueCode, PlanVerdict
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.scope_guard import validate_imat_pack
from app.ca_imat_eapcet.scoring import score_imat_decimal
from app.ca_imat_eapcet.verdict_combine import combine_verdicts


class ImatPaperPlanner:
    """D14-16..20: IMAT profile with decimal scoring and section allocation."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: ImatPaperPlanRequest) -> ImatPaperPlanResult:
        pack_issues = validate_imat_pack(request.exam_pack_code)
        if pack_issues:
            return ImatPaperPlanResult(
                verdict=PlanVerdict.FAIL,
                total_questions=0,
                delivered_count=0,
                sections={},
                decimal_total_marks=0.0,
                issue_codes=pack_issues,
            )

        target = request.requested_count or IMAT_TOTAL_QUESTIONS
        alloc = self._practice.allocate(
            AllocateRequest(
                exam_pack_code=request.exam_pack_code,
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
        issues = list(alloc.issue_codes)
        if target == IMAT_TOTAL_QUESTIONS and alloc.delivered_count != IMAT_TOTAL_QUESTIONS:
            issues.append(IssueCode.IMAT_COUNT_MISMATCH)
            verdict = combine_verdicts(verdict, PlanVerdict.SHORTAGE)

        structural_only = bool(alloc.metadata_json.get("structural_demonstration_only"))
        if structural_only and target == IMAT_TOTAL_QUESTIONS:
            verdict = combine_verdicts(verdict, PlanVerdict.REVIEW_REQUIRED)

        return ImatPaperPlanResult(
            verdict=verdict,
            total_questions=target,
            delivered_count=alloc.delivered_count,
            sections=sections,
            decimal_total_marks=float(decimal_total.quantize(Decimal("0.1"))),
            issue_codes=issues,
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "options_per_question": 5,
                "structural_demonstration_only": structural_only,
            },
        )