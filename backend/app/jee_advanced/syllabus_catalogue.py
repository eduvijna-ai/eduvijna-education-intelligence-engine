"""Versioned official syllabus catalogue (D12-09/D12-10) — verified mappings only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import SOURCE_SLOT_SYLLABUS, VERSION_REFERENCE_2026
from app.jee_advanced.source_authority import evaluate_slot_authority
from app.models.curriculum import LearningOutcome
from app.models.enums import SourceRevisionStatus


class CatalogueStatus(StrEnum):
    SOURCE_PENDING = "source_pending"
    MAPPING_REVIEW_PENDING = "mapping_review_pending"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class SyllabusTopicRef:
    subject_code: str
    topic_code: str
    concept_label: str
    source_page_locator: str | None
    derived_group: str | None = None
    learning_outcome_id: str | None = None


@dataclass(frozen=True, slots=True)
class SyllabusCatalogueReport:
    status: CatalogueStatus
    exam_version_code: str
    topics: tuple[SyllabusTopicRef, ...]
    issue_codes: tuple[str, ...]


def build_reference_syllabus_catalogue(session: Session) -> SyllabusCatalogueReport:
    """READY only when slot authority trusted, page locator present, and LO rows exist."""

    slot_auth = evaluate_slot_authority(session, SOURCE_SLOT_SYLLABUS)
    if not slot_auth.trusted or slot_auth.revision_id is None:
        return SyllabusCatalogueReport(
            status=CatalogueStatus.SOURCE_PENDING,
            exam_version_code=VERSION_REFERENCE_2026,
            topics=(),
            issue_codes=slot_auth.issues or ("syllabus_source_not_trusted",),
        )

    from app.models import SourceRevision

    revision = session.get(SourceRevision, slot_auth.revision_id)
    if revision is None or revision.status != SourceRevisionStatus.ACTIVE.value:
        return SyllabusCatalogueReport(
            status=CatalogueStatus.SOURCE_PENDING,
            exam_version_code=VERSION_REFERENCE_2026,
            topics=(),
            issue_codes=("syllabus_revision_not_active",),
        )

    meta = revision.metadata_json or {}
    page_locator = str(
        meta.get("page_locator") or meta.get("official_page_reference") or ""
    ).strip()
    if not page_locator:
        return SyllabusCatalogueReport(
            status=CatalogueStatus.MAPPING_REVIEW_PENDING,
            exam_version_code=VERSION_REFERENCE_2026,
            topics=(),
            issue_codes=("syllabus_page_locator_missing",),
        )

    outcomes = session.scalars(
        select(LearningOutcome).where(
            LearningOutcome.source_revision_id == str(revision.id),
            LearningOutcome.active.is_(True),
        )
    ).all()
    if not outcomes:
        return SyllabusCatalogueReport(
            status=CatalogueStatus.MAPPING_REVIEW_PENDING,
            exam_version_code=VERSION_REFERENCE_2026,
            topics=(),
            issue_codes=("learning_outcome_links_missing",),
        )

    topics = [
        SyllabusTopicRef(
            subject_code=str((lo.metadata_json or {}).get("subject_code") or "unknown"),
            topic_code=lo.code,
            concept_label=lo.text[:256],
            source_page_locator=lo.source_locator or page_locator,
            derived_group=str((lo.metadata_json or {}).get("derived_group") or "") or None,
            learning_outcome_id=str(lo.id),
        )
        for lo in outcomes
    ]
    return SyllabusCatalogueReport(
        status=CatalogueStatus.READY,
        exam_version_code=VERSION_REFERENCE_2026,
        topics=tuple(topics),
        issue_codes=(),
    )


def learning_outcome_bindings_available(session: Session) -> tuple[bool, tuple[str, ...]]:
    """D12-10: requires READY catalogue with persisted LO links — no invented equivalence."""

    report = build_reference_syllabus_catalogue(session)
    if report.status != CatalogueStatus.READY:
        return False, report.issue_codes
    if not report.topics or not all(t.learning_outcome_id for t in report.topics):
        return False, ("learning_outcome_bindings_incomplete",)
    return True, ()