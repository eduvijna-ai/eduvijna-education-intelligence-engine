"""Reviewed concept→LO→competency graph checks for reference syllabus (PROD-47-02)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import OFFICIAL_SUBJECTS
from app.models.curriculum import ConceptPrerequisite, CurriculumNode, LearningOutcome
from app.models.enums import CurriculumNodeType
from app.models.framework_structure import LearningOutcomeCompetencyLink


def _concept_id_for_outcome(session: Session, lo: LearningOutcome) -> str | None:
    meta = dict(lo.metadata_json or {})
    concept_id = str(meta.get("concept_node_id") or "").strip()
    if concept_id:
        return concept_id
    if lo.nodes:
        for node in lo.nodes:
            if node.node_type == CurriculumNodeType.CONCEPT.value:
                return str(node.id)
    return None


def syllabus_graph_issue_codes(
    session: Session,
    *,
    outcomes: Sequence[LearningOutcome],
    organization_id: str | None = None,
    curriculum_version_id: str | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not outcomes:
        issues.append("learning_outcome_links_missing")
        return tuple(issues)

    subjects_seen: set[str] = set()

    for lo in outcomes:
        meta = dict(lo.metadata_json or {})
        subject = str(meta.get("subject_code") or "").strip().lower()
        if not subject or subject == "unknown":
            issues.append("lo_subject_unknown")
        elif subject not in {s.lower() for s in OFFICIAL_SUBJECTS}:
            issues.append(f"lo_subject_unmapped:{lo.code}")
        else:
            subjects_seen.add(subject)

        if organization_id:
            lo_org = str(meta.get("organization_id") or "").strip()
            if lo_org and lo_org != organization_id:
                issues.append("lo_tenant_mismatch")

        if not (lo.source_locator or "").strip():
            issues.append("lo_source_locator_missing")

        if curriculum_version_id and str(lo.curriculum_version_id) != curriculum_version_id:
            issues.append("lo_curriculum_version_mismatch")

        concept_id = _concept_id_for_outcome(session, lo)
        if not concept_id:
            issues.append("concept_mapping_missing")
            continue

        concept = session.get(CurriculumNode, concept_id)
        if concept is None:
            issues.append("concept_node_not_found")
            continue
        if concept.node_type != CurriculumNodeType.CONCEPT.value:
            issues.append("concept_node_wrong_type")
        if curriculum_version_id and str(concept.curriculum_version_id) != curriculum_version_id:
            issues.append("concept_version_mismatch")
        if not (concept.source_locator or "").strip():
            issues.append("concept_source_locator_missing")

        prereq_id = str(meta.get("prerequisite_concept_id") or "").strip()
        if prereq_id:
            edge = session.scalar(
                select(ConceptPrerequisite).where(
                    ConceptPrerequisite.target_concept_id == concept_id,
                    ConceptPrerequisite.prerequisite_concept_id == prereq_id,
                )
            )
            if edge is None:
                issues.append("concept_prerequisite_missing")

        if not meta.get("mapping_reviewed"):
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
            if link.publication_status != "final":
                issues.append("competency_link_not_final")
            if link.status not in {"direct", "partial"}:
                issues.append("competency_link_status_invalid")
            if link.status == "direct" and not (link.evidence_text or "").strip():
                issues.append("competency_link_evidence_missing")
            if curriculum_version_id and str(link.curriculum_version_id) != curriculum_version_id:
                issues.append("competency_link_version_mismatch")
            if lo.source_revision_id and str(link.source_revision_id) != str(lo.source_revision_id):
                issues.append("competency_link_source_drift")

    for subj in OFFICIAL_SUBJECTS:
        if subj.lower() not in subjects_seen:
            issues.append(f"pcm_subject_missing:{subj.lower()}")

    return tuple(dict.fromkeys(issues))