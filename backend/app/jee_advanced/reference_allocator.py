"""D12-CORE-04: Reference two-paper allocation from trusted persisted questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.constants import PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.enums import AdvancedIssueCode, AdvancedPlanVerdict
from app.jee_advanced.persisted_practice import select_trusted_questions
from app.jee_advanced.source_registry import reference_evidence_ready


@dataclass(frozen=True, slots=True)
class ReferenceAllocationRequest:
    organization_id: str
    institution_id: str | None
    exam_version_id: str
    paper_quotas: dict[str, dict[str, int]]


@dataclass(frozen=True, slots=True)
class ReferenceAllocationResult:
    verdict: AdvancedPlanVerdict
    paper_item_ids: dict[str, list[str]]
    issue_codes: tuple[AdvancedIssueCode, ...]
    metadata_json: dict[str, Any]


def allocate_reference_two_paper(
    session: Session,
    request: ReferenceAllocationRequest,
) -> ReferenceAllocationResult:
    if not reference_evidence_ready(session):
        return ReferenceAllocationResult(
            verdict=AdvancedPlanVerdict.SOURCE_PENDING,
            paper_item_ids={},
            issue_codes=(AdvancedIssueCode.UNAPPROVED_SOURCE,),
            metadata_json={"mode": "reference", "demonstration_only": False},
        )

    expected = {PAPER_1_CODE, PAPER_2_CODE}
    if set(request.paper_quotas.keys()) != expected:
        return ReferenceAllocationResult(
            verdict=AdvancedPlanVerdict.FAIL,
            paper_item_ids={},
            issue_codes=(AdvancedIssueCode.INVALID_PAPER_CODE,),
            metadata_json={},
        )

    used: set[str] = set()
    out: dict[str, list[str]] = {}
    issues: list[AdvancedIssueCode] = []
    for paper_code in (PAPER_1_CODE, PAPER_2_CODE):
        quotas = request.paper_quotas[paper_code]
        paper_ids: list[str] = []
        for subject_code, count in quotas.items():
            if count <= 0:
                issues.append(AdvancedIssueCode.INVALID_REQUESTED_COUNT)
                continue
            refs, sel_issues, verdict = select_trusted_questions(
                session,
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                exam_version_id=request.exam_version_id,
                subject_code=subject_code,
                topic_group=None,
                requested_count=count,
            )
            issues.extend(sel_issues)
            if verdict is not AdvancedPlanVerdict.PASS:
                return ReferenceAllocationResult(
                    verdict=verdict,
                    paper_item_ids=out,
                    issue_codes=tuple(issues),
                    metadata_json={"partial_paper": paper_code},
                )
            for ref in refs:
                if ref.question_id in used:
                    issues.append(AdvancedIssueCode.DUPLICATE_CROSS_PAPER)
                    return ReferenceAllocationResult(
                        verdict=AdvancedPlanVerdict.FAIL,
                        paper_item_ids=out,
                        issue_codes=tuple(issues),
                        metadata_json={"duplicate_id": ref.question_id},
                    )
                used.add(ref.question_id)
                paper_ids.append(ref.question_id)
        out[paper_code] = paper_ids

    if issues:
        return ReferenceAllocationResult(
            verdict=AdvancedPlanVerdict.FAIL,
            paper_item_ids=out,
            issue_codes=tuple(issues),
            metadata_json={},
        )

    return ReferenceAllocationResult(
        verdict=AdvancedPlanVerdict.PASS,
        paper_item_ids=out,
        issue_codes=(),
        metadata_json={
            "mode": "reference",
            "demonstration_only": False,
            "source_attested": True,
        },
    )
