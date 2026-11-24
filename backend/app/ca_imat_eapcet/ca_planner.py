from __future__ import annotations

import hashlib

from app.ca_imat_eapcet.authority import resolve_ca_authority
from app.ca_imat_eapcet.ca_descriptive import allocate_descriptive_items
from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    CA_PAPER_CODES,
    CA_PAPER_KIND,
)
from app.ca_imat_eapcet.contracts import (
    AllocateRequest,
    AllocateResult,
    CaPaperPlanRequest,
    CaPaperPlanResult,
)
from app.ca_imat_eapcet.enums import Day14ProfileKind, Day14SourceTrustMode, IssueCode, PlanVerdict
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.request_guards import validate_requested_count
from app.ca_imat_eapcet.scope_guard import validate_ca_pack
from app.ca_imat_eapcet.verdict_combine import combine_verdicts


class CaFoundationPlanner:
    """D14-06..15: four-paper CA Foundation planning with exact-count or typed shortage."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: CaPaperPlanRequest) -> CaPaperPlanResult:
        issues = list(validate_ca_pack(request.exam_pack_code))
        if request.exam_pack_code != CA_FOUNDATION_PACK_CODE:
            issues.append(IssueCode.WRONG_EXAM_PACK)

        authority = resolve_ca_authority(
            profile_kind=request.profile_kind,
            session_code=request.session_code,
        )
        if authority.verdict and request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
            return CaPaperPlanResult(
                verdict=authority.verdict,
                papers={},
                total_marks=0,
                issue_codes=list(authority.issue_codes),
                metadata_json={"demonstration_only": False},
            )

        papers_requested = request.papers or list(CA_PAPER_CODES)
        if len(set(papers_requested)) != len(papers_requested):
            issues.append(IssueCode.DUPLICATE_QUESTION)

        paper_results: dict[str, AllocateResult] = {}
        all_issues: list[IssueCode] = []
        total_marks = 0.0
        paper_verdicts: list[PlanVerdict] = []

        per_paper = request.items_per_paper or 5
        count_issues = validate_requested_count(per_paper)
        issues.extend(count_issues)

        for paper in papers_requested:
            if CA_PAPER_KIND.get(paper) == "descriptive":
                d_verdict, delivered, items, d_issues = allocate_descriptive_items(
                    paper_code=paper,
                    requested_count=1,
                )
                marks = sum(i.total_marks for i in items)
                total_marks += marks
                paper_results[paper] = AllocateResult(
                    verdict=d_verdict,
                    requested_count=1,
                    delivered_count=delivered,
                    questions=[],
                    issue_codes=d_issues,
                    checksum=items[0].item_id if items else "",
                    metadata_json={
                        "descriptive": True,
                        "descriptive_payload": [i.model_dump() for i in items],
                        "automated_grading_claimed": False,
                    },
                )
                paper_verdicts.append(d_verdict)
                all_issues.extend(d_issues)
                continue

            result = self._practice.allocate(
                AllocateRequest(
                    exam_pack_code=CA_FOUNDATION_PACK_CODE,
                    profile_kind=request.profile_kind,
                    trust_mode=request.trust_mode,
                    paper_or_section=paper,
                    requested_count=per_paper,
                    session_code=request.session_code,
                )
            )
            for q in result.questions:
                total_marks += q.marks_if_correct
            paper_results[paper] = result
            paper_verdicts.append(result.verdict)
            all_issues.extend(result.issue_codes)

        if not paper_results:
            return CaPaperPlanResult(
                verdict=PlanVerdict.FAIL,
                papers={},
                total_marks=0,
                issue_codes=issues,
                metadata_json={"structural_demonstration_only": True},
            )

        bundle_verdict = combine_verdicts(*paper_verdicts)
        if issues:
            bundle_verdict = combine_verdicts(bundle_verdict, PlanVerdict.FAIL)

        return CaPaperPlanResult(
            verdict=bundle_verdict,
            papers=paper_results,
            total_marks=int(total_marks),
            issue_codes=list(dict.fromkeys(issues + all_issues)),
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "structural_demonstration_only": bundle_verdict is not PlanVerdict.PASS,
                "bundle_checksum": hashlib.sha256(
                    "".join(r.checksum for r in paper_results.values()).encode()
                ).hexdigest()[:24],
            },
        )