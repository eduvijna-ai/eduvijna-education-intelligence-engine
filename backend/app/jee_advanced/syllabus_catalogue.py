"""Versioned official syllabus catalogue (D12-09/D12-10) — metadata only until ACTIVE revision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    OFFICIAL_SUBJECTS,
    SOURCE_SLOT_SYLLABUS,
    VERSION_REFERENCE_2026,
)
from app.jee_advanced.source_registry import _find_slot_source
from app.models import SourceRevision
from app.models.enums import SourceRevisionStatus


class CatalogueStatus(StrEnum):
    SOURCE_PENDING = "source_pending"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class SyllabusTopicRef:
    subject_code: str
    topic_code: str
    concept_label: str
    source_page_locator: str | None
    derived_group: str | None = None


@dataclass(frozen=True, slots=True)
class SyllabusCatalogueReport:
    status: CatalogueStatus
    exam_version_code: str
    topics: tuple[SyllabusTopicRef, ...]
    issue_codes: tuple[str, ...]


def _active_syllabus_revision(session: Session) -> SourceRevision | None:
    source = _find_slot_source(session, SOURCE_SLOT_SYLLABUS)
    if source is None:
        return None
    return session.scalar(
        select(SourceRevision)
        .where(
            SourceRevision.source_id == source.id,
            SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
        )
        .order_by(SourceRevision.revision_number.desc())
    )


def build_reference_syllabus_catalogue(session: Session) -> SyllabusCatalogueReport:
    """Return page-locator catalogue only when an ACTIVE official syllabus revision exists."""

    revision = _active_syllabus_revision(session)
    if revision is None:
        return SyllabusCatalogueReport(
            status=CatalogueStatus.SOURCE_PENDING,
            exam_version_code=VERSION_REFERENCE_2026,
            topics=(),
            issue_codes=("syllabus_active_revision_missing",),
        )
    meta = revision.metadata_json or {}
    page_locator = str(meta.get("page_locator") or "").strip() or None
    topics: list[SyllabusTopicRef] = []
    for subject in OFFICIAL_SUBJECTS:
        topics.append(
            SyllabusTopicRef(
                subject_code=subject,
                topic_code=f"{subject}.official_root",
                concept_label=f"{subject} (official syllabus root)",
                source_page_locator=page_locator,
                derived_group=None,
            )
        )
    return SyllabusCatalogueReport(
        status=CatalogueStatus.READY,
        exam_version_code=VERSION_REFERENCE_2026,
        topics=tuple(topics),
        issue_codes=(),
    )


def learning_outcome_bindings_available(session: Session) -> tuple[bool, tuple[str, ...]]:
    """D12-10: canonical LO linkage requires ACTIVE syllabus — no invented equivalence."""

    report = build_reference_syllabus_catalogue(session)
    if report.status != CatalogueStatus.READY:
        return False, report.issue_codes
    return True, ()