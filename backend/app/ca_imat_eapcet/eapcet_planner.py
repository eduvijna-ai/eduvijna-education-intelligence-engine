from __future__ import annotations

from app.ca_imat_eapcet.constants import (
    EAPCET_TOTAL_MINUTES,
    EAPCET_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.contracts import (
    AllocateRequest,
    EapcetPaperPlanRequest,
    EapcetPaperPlanResult,
)
from app.ca_imat_eapcet.eapcet_bilingual import (
    BilingualVerdict,
    evaluate_bilingual_pair,
    validate_bilingual_medium,
)
from app.ca_imat_eapcet.enums import Day14SourceTrustMode, EapcetStream, IssueCode, PlanVerdict
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.scope_guard import validate_eapcet_pack
from app.ca_imat_eapcet.verdict_combine import combine_verdicts


class EapcetPaperPlanner:
    """D14-21..25: stream-specific 160-question papers."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: EapcetPaperPlanRequest) -> EapcetPaperPlanResult:
        pack_issues = validate_eapcet_pack(request.exam_pack_code)
        if pack_issues:
            return EapcetPaperPlanResult(
                verdict=PlanVerdict.FAIL,
                stream=request.stream,
                total_questions=0,
                delivered_count=0,
                section_counts={},
                duration_minutes=EAPCET_TOTAL_MINUTES,
                issue_codes=pack_issues,
            )

        if request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE:
            medium_issues = validate_bilingual_medium(request.medium_pair)
            bilingual = BilingualVerdict(
                verdict=PlanVerdict.PASS if not medium_issues else PlanVerdict.REVIEW_REQUIRED,
                issue_codes=tuple(medium_issues),
            )
        else:
            bilingual = evaluate_bilingual_pair(request.medium_pair)
        target = request.requested_count or EAPCET_TOTAL_QUESTIONS
        alloc = self._practice.allocate(
            AllocateRequest(
                exam_pack_code=request.exam_pack_code,
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                paper_or_section="full_paper",
                requested_count=target,
                academic_year=request.exam_year,
                stream=request.stream,
            )
        )

        section_counts: dict[str, int] = {}
        for q in alloc.questions:
            section_counts[q.paper_or_section] = section_counts.get(q.paper_or_section, 0) + 1

        issues = list(alloc.issue_codes) + list(bilingual.issue_codes)
        verdict = combine_verdicts(alloc.verdict, bilingual.verdict)

        unofficial = request.trust_mode is not Day14SourceTrustMode.SYNTHETIC_FIXTURE
        if request.stream is EapcetStream.ENGINEERING and unofficial:
            issues.append(IssueCode.EAPCET_OFFICIAL_UNATTESTED)
            verdict = combine_verdicts(verdict, PlanVerdict.SOURCE_PENDING)

        if target == EAPCET_TOTAL_QUESTIONS and alloc.delivered_count != EAPCET_TOTAL_QUESTIONS:
            issues.append(IssueCode.EAPCET_COUNT_MISMATCH)
            verdict = combine_verdicts(verdict, PlanVerdict.SHORTAGE)

        structural_only = bool(alloc.metadata_json.get("structural_demonstration_only"))
        if structural_only and any(
            q.paper_or_section == "botany" for q in alloc.questions
        ):
            pass  # AP stream partial validation expected for some sections

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
                "bilingual_verdict": bilingual.verdict.value,
                "structural_demonstration_only": structural_only,
            },
        )