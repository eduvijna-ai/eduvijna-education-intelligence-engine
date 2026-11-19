"""D12-CORE-04: Reference two-paper allocation from trusted persisted questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    OFFICIAL_SUBJECTS,
    PAPER_1_CODE,
    PAPER_2_CODE,
    VERSION_REFERENCE_2026,
)
from app.jee_advanced.enums import AdvancedIssueCode, AdvancedPlanVerdict
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models import ExamBlueprintRule, ExamVersion
from app.models.enums import BlueprintRuleType


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


def _reference_blueprint_ready(session: Session, exam_version_id: str) -> bool:
    version = session.get(ExamVersion, exam_version_id)
    if version is None:
        return False
    if version.version_code != VERSION_REFERENCE_2026:
        return False

    rules = session.scalars(
        select(ExamBlueprintRule).where(
            ExamBlueprintRule.exam_version_id == exam_version_id,
            ExamBlueprintRule.rule_type.in_(
                (
                    BlueprintRuleType.QUESTION_COUNT.value,
                    BlueprintRuleType.TOPIC_DISTRIBUTION.value,
                    BlueprintRuleType.SCORING.value,
                )
            ),
        )
    ).all()
    by_paper: dict[str, set[str]] = {PAPER_1_CODE: set(), PAPER_2_CODE: set()}
    for rule in rules:
        meta = dict(rule.metadata_json or {})
        paper = str(meta.get("paper_code") or "").strip()
        if paper not in by_paper:
            continue
        if not rule.exact_count and rule.min_count is None:
            continue
        pinned = str((rule.selector_json or {}).get("source_pinned_revision_id") or "")
        if not pinned:
            continue
        by_paper[paper].add(rule.rule_type)
        subjects = meta.get("subjects") or OFFICIAL_SUBJECTS
        if set(str(s).lower() for s in subjects) != set(OFFICIAL_SUBJECTS):
            return False

    return all(by_paper[code] for code in (PAPER_1_CODE, PAPER_2_CODE))


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

    if not _reference_blueprint_ready(session, request.exam_version_id):
        return ReferenceAllocationResult(
            verdict=AdvancedPlanVerdict.REVIEW_REQUIRED,
            paper_item_ids={},
            issue_codes=(AdvancedIssueCode.BLUEPRINT_UNPINNED,),
            metadata_json={
                "mode": "reference",
                "reason": "approved_two_paper_blueprint_missing",
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