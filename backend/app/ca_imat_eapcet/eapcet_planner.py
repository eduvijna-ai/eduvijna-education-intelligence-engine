from __future__ import annotations

from app.ca_imat_eapcet.constants import (
    EAPCET_PACK_CODE,
    EAPCET_TOTAL_MINUTES,
    EAPCET_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.contracts import (
    AllocateRequest,
    EapcetPaperPlanRequest,
    EapcetPaperPlanResult,
)
from app.ca_imat_eapcet.eapcet_bilingual import validate_bilingual_medium
from app.ca_imat_eapcet.enums import Day14SourceTrustMode, EapcetStream, IssueCode, PlanVerdict
from app.ca_imat_eapcet.practice_service import Day14PracticeService


class EapcetPaperPlanner:
    """D14-21..25: stream-specific 160-question papers."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: EapcetPaperPlanRequest) -> EapcetPaperPlanResult:
        bilingual_issues = validate_bilingual_medium(request.medium_pair)
        target = request.requested_count or EAPCET_TOTAL_QUESTIONS
        alloc = self._practice.allocate(
            AllocateRequest(
                exam_pack_code=EAPCET_PACK_CODE,
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                paper_or_section=request.stream.value,
                requested_count=target,
                academic_year=request.exam_year,
                stream=request.stream,
            )
        )

        section_counts: dict[str, int] = {}
        for q in alloc.questions:
            section_counts[q.paper_or_section] = section_counts.get(q.paper_or_section, 0) + 1

        verdict = alloc.verdict
        issues = list(alloc.issue_codes) + bilingual_issues
        unofficial = request.trust_mode is not Day14SourceTrustMode.SYNTHETIC_FIXTURE
        if request.stream is EapcetStream.ENGINEERING and unofficial:
            issues.append(IssueCode.EAPCET_OFFICIAL_UNATTESTED)

        if target == EAPCET_TOTAL_QUESTIONS and alloc.delivered_count != EAPCET_TOTAL_QUESTIONS:
            verdict = PlanVerdict.SHORTAGE
            issues.append(IssueCode.EAPCET_COUNT_MISMATCH)

        if bilingual_issues:
            verdict = PlanVerdict.REVIEW_REQUIRED

        return EapcetPaperPlanResult(
            verdict=verdict,
            stream=request.stream,
            total_questions=target,
            delivered_count=alloc.delivered_count,
            section_counts=section_counts,
            duration_minutes=EAPCET_TOTAL_MINUTES,
            issue_codes=list(dict.fromkeys(issues)),
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "engineering_reference_80_40_40": request.stream is EapcetStream.ENGINEERING,
                "medium_pair": request.medium_pair,
            },
        )