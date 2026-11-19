"""D12-CORE-04: Reference two-paper allocation from trusted persisted questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.enums import AdvancedIssueCode, AdvancedPlanVerdict
from app.jee_advanced.reference_blueprint import reference_blueprint_issue_codes
from app.jee_advanced.source_registry import reference_evidence_ready


@dataclass(frozen=True, slots=True)
class ReferenceAllocationRequest:
    organization_id: str
    institution_id: str | None
    exam_version_id: str
    paper_quotas: dict[str, dict[str, int]] | None = None


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

    blueprint_issues = reference_blueprint_issue_codes(session, request.exam_version_id)
    if blueprint_issues:
        return ReferenceAllocationResult(
            verdict=AdvancedPlanVerdict.REVIEW_REQUIRED,
            paper_item_ids={},
            issue_codes=(AdvancedIssueCode.BLUEPRINT_UNPINNED,),
            metadata_json={
                "mode": "reference",
                "reason": "approved_two_paper_blueprint_missing",
                "missing_rules": list(blueprint_issues),
            },
        )

    # Caller quotas are ignored until official blueprint-backed selection is implemented.
    return ReferenceAllocationResult(
        verdict=AdvancedPlanVerdict.SOURCE_PENDING,
        paper_item_ids={},
        issue_codes=(AdvancedIssueCode.UNAPPROVED_SOURCE,),
        metadata_json={
            "mode": "reference",
            "demonstration_only": False,
            "caller_quotas_ignored": bool(request.paper_quotas),
        },
    )