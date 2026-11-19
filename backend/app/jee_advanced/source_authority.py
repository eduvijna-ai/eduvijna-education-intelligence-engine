"""D12-CORE-01: Database-backed JEE Advanced reference source authority (fail-closed)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    COPYRIGHT_RIGHTS_RESERVED_REVIEW,
    JEE_ADVANCED_AUTHORITY,
    SOURCE_SLOT_BROCHURE,
    SOURCE_SLOT_KEY_PAPER1,
    SOURCE_SLOT_KEY_PAPER2,
    SOURCE_SLOT_PAPER1,
    SOURCE_SLOT_PAPER2,
    SOURCE_SLOT_SYLLABUS,
)
from app.jee_advanced.exam_profile import lookup_reference_exam_version
from app.jee_advanced.reference_blueprint import reference_blueprint_issue_codes
from app.jee_advanced.source_curator_verify import authorized_source_curator_verified
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS
from app.jee_advanced.source_storage import metadata_marks_synthetic, official_source_storage
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import (
    SourceExtractionStatus,
    SourceRevisionStatus,
    SourceStatus,
    SourceTrustTier,
    SourceType,
)
from app.source_intelligence.approval_fingerprint import (
    compute_revision_approval_fingerprint,
    verify_revision_stored_source_snapshot_checksum,
)
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

_SLOT_SOURCE_TYPE: dict[str, SourceType] = {
    SOURCE_SLOT_BROCHURE: SourceType.OFFICIAL_EXAM_BULLETIN,
    SOURCE_SLOT_SYLLABUS: SourceType.OFFICIAL_SYLLABUS,
    SOURCE_SLOT_PAPER1: SourceType.OFFICIAL_PAPER,
    SOURCE_SLOT_PAPER2: SourceType.OFFICIAL_PAPER,
    SOURCE_SLOT_KEY_PAPER1: SourceType.ANSWER_KEY,
    SOURCE_SLOT_KEY_PAPER2: SourceType.ANSWER_KEY,
}

_SLOT_PAGE_LOCATOR_KEYS = ("official_page_reference", "page_locator", "discovery_page_ref")

_SLOT_PAPER_CODES: dict[str, str] = {
    SOURCE_SLOT_PAPER1: "paper_1",
    SOURCE_SLOT_PAPER2: "paper_2",
    SOURCE_SLOT_KEY_PAPER1: "paper_1",
    SOURCE_SLOT_KEY_PAPER2: "paper_2",
}


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


def _curator_approve_event(session: Session, revision_id: str) -> SourceAuditEvent | None:
    return session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )


def _approver_is_authorized(
    session: Session, actor_id: str | None, approved_by: str | None
) -> bool:
    if not actor_id or not approved_by:
        return False
    if str(actor_id).strip() != str(approved_by).strip():
        return False
    return authorized_source_curator_verified(session, approved_by)


def _slot_locator_present(source_meta: dict[str, object]) -> bool:
    return any(str(source_meta.get(key) or "").strip() for key in _SLOT_PAGE_LOCATOR_KEYS)


def _pdf_magic_valid(service: SourceIntelligenceService, revision: SourceRevision) -> bool:
    try:
        payload, _, ok = service._content_integrity(revision)
    except Exception:
        return False
    if not ok or not payload:
        return False
    head = payload[:8]
    return head.startswith(b"%PDF")


def _slot_official_policy_issues(
    slot_id: str,
    source: Source,
    revision: SourceRevision,
    *,
    for_official_reference: bool,
) -> list[str]:
    issues: list[str] = []
    expected_type = _SLOT_SOURCE_TYPE.get(slot_id)
    if expected_type is not None and source.source_type != expected_type.value:
        issues.append("wrong_source_type")
    if source.trust_tier != SourceTrustTier.OFFICIAL_PRIMARY.value:
        issues.append("wrong_trust_tier")
    if (source.authority or "").strip().lower() != JEE_ADVANCED_AUTHORITY.lower():
        issues.append("wrong_authority")
    if source.academic_year not in ("2026", "2026-27"):
        issues.append("wrong_academic_year")

    source_meta = dict(source.metadata_json or {})
    revision_meta = dict(revision.metadata_json or {})
    if metadata_marks_synthetic(source_meta) or metadata_marks_synthetic(revision_meta):
        issues.append("synthetic_evidence_marker")

    if for_official_reference:
        if not revision.content_type.lower().startswith("application/pdf"):
            issues.append("not_original_pdf_mime")
        rights = (source.copyright_classification or "").strip()
        meta_rights = str(source_meta.get("copyright_classification") or "").strip()
        if not rights:
            issues.append("missing_rights_classification")
        elif rights == COPYRIGHT_RIGHTS_RESERVED_REVIEW:
            issues.append("rights_review_pending")
        if meta_rights and meta_rights != rights:
            issues.append("rights_metadata_mismatch")
        if str(source_meta.get("rights_review_status") or "") == "RIGHTS_REVIEW_PENDING":
            issues.append("rights_review_pending")
        if not str(source_meta.get("human_rights_disposition") or "").strip():
            issues.append("human_rights_disposition_missing")
        if not _slot_locator_present(source_meta):
            issues.append("missing_page_locator")
        expected_paper = _SLOT_PAPER_CODES.get(slot_id)
        if expected_paper is not None:
            paper = str(source_meta.get("paper_code") or revision_meta.get("paper_code") or "")
            if paper != expected_paper:
                issues.append("wrong_paper_slot_binding")

    return issues


def evaluate_slot_authority(
    session: Session,
    slot_id: str,
    *,
    for_official_reference: bool = True,
) -> SlotAuthorityResult:
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

    issues.extend(
        _slot_official_policy_issues(
            slot_id, source, revision, for_official_reference=for_official_reference
        )
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

    approve_event = _curator_approve_event(session, str(revision.id))
    if approve_event is None:
        issues.append("missing_curator_approve_audit")
    elif not _approver_is_authorized(
        session, approve_event.actor_id, revision.approved_by
    ):
        issues.append("authorized_curator_not_verified")

    storage = official_source_storage() if for_official_reference else None
    if storage is None:
        issues.append("storage_backend_unavailable")
    else:
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
        elif for_official_reference and not _pdf_magic_valid(service, revision):
            issues.append("pdf_magic_invalid")

    trusted = len(issues) == 0
    return SlotAuthorityResult(
        slot_id=slot_id,
        trusted=trusted,
        revision_id=str(revision.id),
        source_id=str(source.id),
        issues=tuple(issues),
    )


def evaluate_slot_storage_integrity(
    session: Session,
    slot_id: str,
    *,
    storage: LocalSourceStorage,
) -> SlotAuthorityResult:
    """Test-only helper: byte integrity without granting official reference readiness."""

    issues: list[str] = []
    source = _find_slot_source(session, slot_id)
    if source is None:
        return SlotAuthorityResult(slot_id, False, None, None, ("source_missing",))
    revision = _active_revision(session, str(source.id))
    if revision is None:
        return SlotAuthorityResult(slot_id, False, None, str(source.id), ("no_active_revision",))

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

    return SlotAuthorityResult(
        slot_id=slot_id,
        trusted=len(issues) == 0,
        revision_id=str(revision.id),
        source_id=str(source.id),
        issues=tuple(issues),
    )


def evaluate_reference_authority(session: Session | None) -> ReferenceAuthorityReport:
    """All six slots must pass independent persisted checks; read-only (no ensure/create)."""

    if session is None:
        return ReferenceAuthorityReport(
            ready=False,
            issues=("session_required",),
        )

    slot_results: list[SlotAuthorityResult] = []
    flat_issues: list[str] = []
    with session.no_autoflush:
        for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
            result = evaluate_slot_authority(
                session, slot.slot_id, for_official_reference=True
            )
            slot_results.append(result)
            if not result.trusted:
                flat_issues.extend(f"{slot.slot_id}:{issue}" for issue in result.issues)

        slots_ready = all(r.trusted for r in slot_results) and len(slot_results) == len(
            JEE_ADVANCED_2026_SOURCE_SLOTS
        )
        ready = slots_ready

        if slots_ready:
            ref_version = lookup_reference_exam_version(session)
            if ref_version is None:
                ready = False
                flat_issues.append("reference_exam_version_missing")
            else:
                blueprint_issues = reference_blueprint_issue_codes(session, str(ref_version.id))
                if blueprint_issues:
                    ready = False
                    flat_issues.extend(f"reference_blueprint:{code}" for code in blueprint_issues)
        elif not flat_issues:
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
    result = evaluate_slot_authority(session, slot_id, for_official_reference=True)
    return result.trusted and result.revision_id == revision_id