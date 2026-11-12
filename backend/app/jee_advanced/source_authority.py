"""D12-CORE-01: Database-backed JEE Advanced reference source authority (fail-closed)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import SourceExtractionStatus, SourceRevisionStatus, SourceStatus
from app.source_intelligence.approval_fingerprint import (
    compute_revision_approval_fingerprint,
    verify_revision_stored_source_snapshot_checksum,
)
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


@dataclass(frozen=True, slots=True)
class SlotAuthorityResult:
    slot_id: str
    trusted: bool
    revision_id: str | None
    source_id: str | None
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceAuthorityReport:
    ready: bool
    slots: tuple[SlotAuthorityResult, ...] = ()
    issues: tuple[str, ...] = field(default_factory=tuple)


def _find_slot_source(session: Session, slot_id: str) -> Source | None:
    candidates = session.scalars(
        select(Source).where(Source.board_or_exam == "jee_advanced")
    ).all()
    for source in candidates:
        if source.metadata_json.get("slot_id") == slot_id:
            return source
    return None


def _active_revision(session: Session, source_id: str) -> SourceRevision | None:
    return session.scalar(
        select(SourceRevision)
        .where(
            SourceRevision.source_id == source_id,
            SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
        )
        .order_by(SourceRevision.revision_number.desc())
    )


def _has_curator_approve_audit(session: Session, revision_id: str) -> bool:
    event = session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )
    if event is None:
        return False
    return bool(event.actor_id and str(event.actor_id).strip())


def evaluate_slot_authority(session: Session, slot_id: str) -> SlotAuthorityResult:
    """Independently verify one required 2026 evidence slot from persisted records."""

    issues: list[str] = []
    source = _find_slot_source(session, slot_id)
    if source is None:
        return SlotAuthorityResult(
            slot_id=slot_id,
            trusted=False,
            revision_id=None,
            source_id=None,
            issues=("source_missing",),
        )

    if source.status != SourceStatus.ACTIVE.value:
        issues.append("source_not_active")
    meta = source.metadata_json or {}
    if not meta.get("jee_advanced_slot"):
        issues.append("not_jee_advanced_slot")
    if str(meta.get("slot_id") or "") != slot_id:
        issues.append("slot_id_mismatch")
    if source.board_or_exam != "jee_advanced":
        issues.append("wrong_board_or_exam")
    if source.academic_year not in ("2026", "2026-27"):
        issues.append("wrong_academic_year")

    revision = _active_revision(session, str(source.id))
    if revision is None:
        issues.append("no_active_revision")
        return SlotAuthorityResult(
            slot_id=slot_id,
            trusted=False,
            revision_id=None,
            source_id=str(source.id),
            issues=tuple(issues),
        )

    if revision.status != SourceRevisionStatus.ACTIVE.value:
        issues.append("revision_not_active")
    if revision.extraction_status != SourceExtractionStatus.SUCCEEDED.value:
        issues.append("extraction_not_succeeded")
    if revision.byte_size <= 0:
        issues.append("empty_byte_size")
    if not revision.storage_path:
        issues.append("missing_storage_path")
    if not revision.validated_checksum or not revision.extracted_checksum:
        issues.append("missing_validation_checksums")
    if not revision.approved_by:
        issues.append("missing_approved_by")
    if not revision.approval_fingerprint:
        issues.append("missing_approval_fingerprint")

    expected_fp = compute_revision_approval_fingerprint(session, revision)
    if revision.approval_fingerprint != expected_fp:
        issues.append("approval_fingerprint_mismatch")

    if not verify_revision_stored_source_snapshot_checksum(revision):
        issues.append("source_snapshot_checksum_invalid")

    if not _has_curator_approve_audit(session, str(revision.id)):
        issues.append("missing_curator_approve_audit")

    storage = session.info.get("jee_core_storage")
    if not isinstance(storage, LocalSourceStorage):
        issues.append("storage_backend_unavailable")
        return SlotAuthorityResult(
            slot_id=slot_id,
            trusted=False,
            revision_id=str(revision.id),
            source_id=str(source.id),
            issues=tuple(issues),
        )
    service = SourceIntelligenceService(session, storage=storage)
    try:
        _, actual_checksum, integrity_ok = service._content_integrity(revision)
    except Exception:
        issues.append("storage_unreadable")
        integrity_ok = False
        actual_checksum = ""

    if not integrity_ok:
        issues.append("stored_bytes_integrity_failed")
    elif revision.checksum != actual_checksum:
        issues.append("checksum_mismatch")
    elif revision.validated_checksum != actual_checksum:
        issues.append("validated_checksum_drift")

    trusted = len(issues) == 0
    return SlotAuthorityResult(
        slot_id=slot_id,
        trusted=trusted,
        revision_id=str(revision.id),
        source_id=str(source.id),
        issues=tuple(issues),
    )


def evaluate_reference_authority(session: Session | None) -> ReferenceAuthorityReport:
    """All six slots must pass independent persisted checks; no module-global overlay."""

    if session is None:
        return ReferenceAuthorityReport(
            ready=False,
            issues=("session_required",),
        )

    slot_results: list[SlotAuthorityResult] = []
    flat_issues: list[str] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        result = evaluate_slot_authority(session, slot.slot_id)
        slot_results.append(result)
        if not result.trusted:
            flat_issues.extend(f"{slot.slot_id}:{issue}" for issue in result.issues)

    ready = all(r.trusted for r in slot_results) and len(slot_results) == len(
        JEE_ADVANCED_2026_SOURCE_SLOTS
    )
    if not ready and not flat_issues:
        flat_issues.append("incomplete_slot_set")

    return ReferenceAuthorityReport(
        ready=ready,
        slots=tuple(slot_results),
        issues=tuple(flat_issues),
    )


def reference_evidence_ready(session: Session | None) -> bool:
    """Fail closed without an explicit database session."""

    return evaluate_reference_authority(session).ready


def evaluate_revision_trusted(session: Session, revision_id: str) -> bool:
    """True when a specific revision satisfies the full curator + bytes authority chain."""

    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return False
    source = revision.source
    if source is None:
        return False
    slot_id = str((source.metadata_json or {}).get("slot_id") or "")
    if not slot_id:
        return False
    result = evaluate_slot_authority(session, slot_id)
    return result.trusted and result.revision_id == revision_id
