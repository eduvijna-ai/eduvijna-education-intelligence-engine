"""Private JEE Advanced 2026 six-slot URL discovery and staging (SRC-02…04; no curator approval)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    COPYRIGHT_RIGHTS_RESERVED_REVIEW,
    JEE_ADVANCED_AUTHORITY,
    JEE_ADVANCED_OFFICIAL_HOST,
    SOURCE_SLOT_KEY_PAPER1,
    SOURCE_SLOT_KEY_PAPER2,
    SOURCE_SLOT_PAPER1,
    SOURCE_SLOT_PAPER2,
)
from app.jee_advanced.source_lifecycle import register_discovery_sources
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    SourceSlotDescriptor,
    _find_slot_source,
)
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import SourceRevisionStatus
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.security import SourceFetchError, UnsafeSourceUrl
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


class SlotLifecycleStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    FETCH_BLOCKED = "FETCH_BLOCKED"
    STAGED = "STAGED"
    STAGED_WITH_ISSUES = "STAGED_WITH_ISSUES"
    CURATOR_PENDING = "CURATOR_PENDING"
    RIGHTS_REVIEW_PENDING = "RIGHTS_REVIEW_PENDING"


MANUAL_UPLOAD_INSTRUCTION = (
    "Place the original PDF bytes under SOURCE_STORAGE_DIR via "
    "SourceIntelligenceService.ingest_upload (PDF method) after Founder confirms "
    "rights; never commit PDFs to Git."
)


@dataclass(frozen=True, slots=True)
class SlotStagingReport:
    slot_id: str
    lifecycle_status: str
    discovery_url: str | None
    final_url: str | None
    sha256: str | None
    byte_size: int | None
    content_type: str | None
    source_id: str | None
    revision_id: str | None
    rights_status: str
    curator_status: str
    issue_codes: tuple[str, ...]
    pdf_magic_valid: bool


def export_src01_manifest() -> list[dict[str, Any]]:
    """SRC-01: direct-URL manifest with slot metadata (no byte claims)."""

    rows: list[dict[str, Any]] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        rows.append(
            {
                "slot_id": slot.slot_id,
                "title": slot.title,
                "direct_pdf_url": slot.discovery_url,
                "document_role": slot.document_role,
                "source_type": slot.source_type_label,
                "source_authority": JEE_ADVANCED_AUTHORITY,
                "academic_year": "2026",
                "paper_code": slot.paper_code,
                "language": slot.language,
                "official_host": JEE_ADVANCED_OFFICIAL_HOST,
                "copyright_classification": COPYRIGHT_RIGHTS_RESERVED_REVIEW,
                "rights_review_status": slot.rights_review_status,
                "staged_bytes_known": False,
            }
        )
    return rows


def pdf_magic_valid(content: bytes) -> bool:
    return content.startswith(b"%PDF")


def slot_identity_issue_codes(
    slot_id: str,
    *,
    final_url: str | None,
    filename: str | None,
    content: bytes,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not pdf_magic_valid(content):
        issues.append("staged_content_not_pdf")
    hint = f"{final_url or ''} {filename or ''}".lower()
    if slot_id == SOURCE_SLOT_PAPER1 and "p2" in hint and "p1" not in hint:
        issues.append("paper_slot_identity_mismatch")
    if slot_id == SOURCE_SLOT_PAPER2 and "p1" in hint and "p2" not in hint:
        issues.append("paper_slot_identity_mismatch")
    if slot_id in {SOURCE_SLOT_KEY_PAPER1, SOURCE_SLOT_KEY_PAPER2}:
        if "solutions" not in hint and "key" not in hint:
            if "english.pdf" in hint or "paper" in hint:
                issues.append("answer_key_question_paper_mixup")
    if slot_id in {SOURCE_SLOT_PAPER1, SOURCE_SLOT_PAPER2} and "solutions" in hint:
        issues.append("question_paper_answer_key_mixup")
    return tuple(issues)


def _ensure_slot_source(
    session: Session,
    service: SourceIntelligenceService,
    slot: SourceSlotDescriptor,
) -> Source:
    existing = _find_slot_source(session, slot.slot_id)
    if existing is not None:
        return existing
    from app.models.enums import SourceTrustTier, SourceType

    if slot.source_type_label == "official_paper":
        source_type = SourceType.OFFICIAL_PAPER
    elif slot.source_type_label == "answer_key":
        source_type = SourceType.ANSWER_KEY
    elif slot.source_type_label == "official_syllabus":
        source_type = SourceType.OFFICIAL_SYLLABUS
    else:
        source_type = SourceType.OFFICIAL_EXAM_BULLETIN

    payload = SourceRegistrationInput(
        source_type=source_type,
        title=slot.title,
        url=slot.discovery_url,
        authority=JEE_ADVANCED_AUTHORITY,
        country="IN",
        board_or_exam="jee_advanced",
        academic_year="2026",
        copyright_classification=COPYRIGHT_RIGHTS_RESERVED_REVIEW,
        trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
        metadata_json={
            "slot_id": slot.slot_id,
            "jee_advanced_slot": True,
            "document_role": slot.document_role,
            "paper_code": slot.paper_code,
            "language": slot.language,
            "rights_review_status": slot.rights_review_status,
            "lifecycle_status": SlotLifecycleStatus.DISCOVERED.value,
            "direct_pdf_url": slot.discovery_url,
            "staged_bytes_authoritative": False,
        },
    )
    return service.register_source(
        payload,
        actor_id="source-ingest-staging",
        request_id=f"src-register-{slot.slot_id}",
    )


def stage_official_slot(
    session: Session,
    service: SourceIntelligenceService,
    slot: SourceSlotDescriptor,
    *,
    actor_id: str = "source-ingest-staging",
    request_id: str | None = None,
) -> SlotStagingReport:
    """Fetch and stage one slot; never approve or activate."""

    if not slot.discovery_url:
        return SlotStagingReport(
            slot_id=slot.slot_id,
            lifecycle_status=SlotLifecycleStatus.FETCH_BLOCKED.value,
            discovery_url=None,
            final_url=None,
            sha256=None,
            byte_size=None,
            content_type=None,
            source_id=None,
            revision_id=None,
            rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
            issue_codes=("missing_direct_pdf_url",),
            pdf_magic_valid=False,
        )

    source = _ensure_slot_source(session, service, slot)
    try:
        revision = service.ingest_url(
            str(source.id),
            url=slot.discovery_url,
            actor_id=actor_id,
            request_id=request_id or f"src-ingest-{slot.slot_id}",
        )
    except (SourceFetchError, UnsafeSourceUrl):
        return SlotStagingReport(
            slot_id=slot.slot_id,
            lifecycle_status=SlotLifecycleStatus.FETCH_BLOCKED.value,
            discovery_url=slot.discovery_url,
            final_url=None,
            sha256=None,
            byte_size=None,
            content_type=None,
            source_id=str(source.id),
            revision_id=None,
            rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
            issue_codes=("FETCH_BLOCKED",),
            pdf_magic_valid=False,
        )

    meta = revision.metadata_json or {}
    final_url = meta.get("final_url")
    filename = revision.original_filename
    identity_issues: tuple[str, ...]
    if not revision.storage_path:
        identity_issues = ("staged_storage_path_missing",)
        return SlotStagingReport(
            slot_id=slot.slot_id,
            lifecycle_status=SlotLifecycleStatus.STAGED_WITH_ISSUES.value,
            discovery_url=slot.discovery_url,
            final_url=str(final_url) if final_url else None,
            sha256=revision.checksum,
            byte_size=revision.byte_size,
            content_type=revision.content_type,
            source_id=str(source.id),
            revision_id=str(revision.id),
            rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
            issue_codes=identity_issues,
            pdf_magic_valid=False,
        )
    content = service.storage.read(revision.storage_path)
    identity_issues = slot_identity_issue_codes(
        slot.slot_id,
        final_url=final_url,
        filename=filename,
        content=content,
    )
    lifecycle = (
        SlotLifecycleStatus.STAGED_WITH_ISSUES.value
        if identity_issues
        else SlotLifecycleStatus.STAGED.value
    )
    return SlotStagingReport(
        slot_id=slot.slot_id,
        lifecycle_status=lifecycle,
        discovery_url=slot.discovery_url,
        final_url=str(final_url) if final_url else None,
        sha256=revision.checksum,
        byte_size=revision.byte_size,
        content_type=revision.content_type,
        source_id=str(source.id),
        revision_id=str(revision.id),
        rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
        curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
        issue_codes=identity_issues,
        pdf_magic_valid=pdf_magic_valid(content),
    )


def stage_all_official_slots_private(
    session: Session,
    storage: LocalSourceStorage,
) -> list[SlotStagingReport]:
    """Stage every manifest slot into private storage; idempotent on identical bytes."""

    register_discovery_sources(session)
    service = SourceIntelligenceService(session, storage=storage)
    return [stage_official_slot(session, service, slot) for slot in JEE_ADVANCED_2026_SOURCE_SLOTS]


def build_redacted_inventory(reports: list[SlotStagingReport]) -> dict[str, Any]:
    return {
        "reference_evidence_ready": False,
        "curator_approval_performed": False,
        "manual_upload_fallback": MANUAL_UPLOAD_INSTRUCTION,
        "slot_count": len(reports),
        "slots": [
            {
                "slot_id": report.slot_id,
                "lifecycle_status": report.lifecycle_status,
                "discovery_url": report.discovery_url,
                "final_url": report.final_url,
                "sha256": report.sha256,
                "byte_size": report.byte_size,
                "content_type": report.content_type,
                "source_id": report.source_id,
                "revision_id": report.revision_id,
                "rights_status": report.rights_status,
                "curator_status": report.curator_status,
                "issue_codes": list(report.issue_codes),
                "pdf_magic_valid": report.pdf_magic_valid,
                "redacted": True,
            }
            for report in reports
        ],
    }


def curator_handback_pending_actions() -> tuple[str, ...]:
    return (
        "Confirm rights_reserved_review_required for redistribution inside Eduvijna.",
        "Provision real AdminActor entries in PolicyRegistry jee_advanced_source_curators@v1.",
        "Review staged SHA-256, paper/year/language identity, and page locators per slot.",
        "Call approve_revision and activate_revision only after human curator signoff.",
        "Complete reference blueprint rules before reference_evidence_ready can be true.",
        "Do not treat public URL reachability as license to publish question text or keys.",
    )


def assert_no_curator_approval_events(session: Session) -> list[str]:
    forbidden = (
        "source_approved",
        "source_activated",
    )
    rows = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.event_type.in_(forbidden),
            SourceAuditEvent.actor_id == "source-ingest-staging",
        )
    ).all()
    return [str(row.id) for row in rows]


def latest_staged_revision(session: Session, slot_id: str) -> SourceRevision | None:
    source = _find_slot_source(session, slot_id)
    if source is None:
        return None
    return session.scalar(
        select(SourceRevision)
        .where(
            SourceRevision.source_id == source.id,
            SourceRevision.status == SourceRevisionStatus.STAGED.value,
        )
        .order_by(SourceRevision.revision_number.desc())
    )