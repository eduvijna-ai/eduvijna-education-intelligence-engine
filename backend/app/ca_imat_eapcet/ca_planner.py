from __future__ import annotations

import hashlib

from app.ca_imat_eapcet.authority import resolve_ca_authority
from app.ca_imat_eapcet.ca_descriptive import demo_descriptive_contracts, validate_descriptive_item
from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    CA_MARKS_PER_PAPER,
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
from app.ca_imat_eapcet.scope_guard import validate_ca_pack


class CaFoundationPlanner:
    """D14-06..15: four-paper CA Foundation planning with exact-count or typed shortage."""

    def __init__(self) -> None:
        self._practice = Day14PracticeService()

    def plan(self, request: CaPaperPlanRequest) -> CaPaperPlanResult:
        issues = list(validate_ca_pack(request.exam_pack_code))
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
        paper_results: dict[str, AllocateResult] = {}
        all_issues: list[IssueCode] = []
        descriptive_by_paper = {d.paper_code: d for d in demo_descriptive_contracts()}
        for paper in papers_requested:
            if CA_PAPER_KIND.get(paper) == "descriptive":
                item = descriptive_by_paper.get(paper)
                if item is None:
                    all_issues.append(IssueCode.WRONG_PAPER)
                    continue
                d_verdict, d_issues = validate_descriptive_item(item)
                paper_results[paper] = AllocateResult(
                    verdict=d_verdict,
                    requested_count=1,
                    delivered_count=1 if d_verdict == PlanVerdict.PASS else 0,
                    questions=[],
                    issue_codes=d_issues,
                    checksum=item.item_id,
                    metadata_json={"descriptive": True, "automated_grading_claimed": False},
                )
                all_issues.extend(d_issues)
                continue
            count = request.items_per_paper or (10 if paper.startswith("paper3") else 5)
            result = self._practice.allocate(
                AllocateRequest(
                    exam_pack_code=CA_FOUNDATION_PACK_CODE,
                    profile_kind=request.profile_kind,
                    trust_mode=request.trust_mode,
                    paper_or_section=paper,
                    requested_count=count,
                    session_code=request.session_code,
                )
            )
            paper_results[paper] = result
            all_issues.extend(result.issue_codes)

        all_pass = all(r.verdict == PlanVerdict.PASS for r in paper_results.values())
        verdict = PlanVerdict.PASS if all_pass and not issues else PlanVerdict.SHORTAGE
        if issues:
            verdict = PlanVerdict.FAIL

        return CaPaperPlanResult(
            verdict=verdict,
            papers=paper_results,
            total_marks=len(paper_results) * CA_MARKS_PER_PAPER,
            issue_codes=list(dict.fromkeys(issues + all_issues)),
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "bundle_checksum": hashlib.sha256(
                    "".join(r.checksum for r in paper_results.values()).encode()
                ).hexdigest()[:24],
            },
        )