"""Reviewed concept→LO→competency graph checks for reference syllabus (READY-02)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import MATHEMATICS_SUBJECT, OFFICIAL_SUBJECTS
from app.models.curriculum import LearningOutcome
from app.models.framework_structure import LearningOutcomeCompetencyLink


def syllabus_graph_issue_codes(
    session: Session,
    *,
    outcomes: Sequence[LearningOutcome],
    organization_id: str | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not outcomes:
        issues.append("learning_outcome_links_missing")
        return tuple(issues)

    for lo in outcomes:
        meta = dict(lo.metadata_json or {})
        subject = str(meta.get("subject_code") or "").strip().lower()
        if not subject or subject == "unknown":
            issues.append("lo_subject_unknown")
        elif subject not in {s.lower() for s in OFFICIAL_SUBJECTS}:
            issues.append(f"lo_subject_unmapped:{lo.code}")

        if organization_id and str(meta.get("organization_id") or "") not in ("", organization_id):
            issues.append("lo_tenant_mismatch")

        if not str(meta.get("concept_node_id") or "").strip():
            issues.append("concept_mapping_missing")
        elif not meta.get("mapping_reviewed"):
            issues.append("mapping_review_pending")

        links = session.scalars(
            select(LearningOutcomeCompetencyLink).where(
                LearningOutcomeCompetencyLink.learning_outcome_id == lo.id
            )
        ).all()
        if not links:
            issues.append("competency_link_missing")
            continue
        for link in links:
            if link.review_status != "reviewed":
                issues.append("competency_link_not_reviewed")
            if link.status == "review_required":
                issues.append("competency_link_review_required")

    has_math = any(
        MATHEMATICS_SUBJECT in str((lo.metadata_json or {}).get("subject_code") or "").lower()
        for lo in outcomes
    )
    if not has_math:
        issues.append("pcm_subject_coverage_incomplete")

    return tuple(dict.fromkeys(issues))