"""Private JEE Advanced 2026 six-slot URL discovery and staging (SRC/STG; no curator approval)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    COPYRIGHT_RIGHTS_RESERVED_REVIEW,
    JEE_ADVANCED_AUTHORITY,
    JEE_ADVANCED_OFFICIAL_HOST,
    SOURCE_SLOT_BROCHURE,
    SOURCE_SLOT_KEY_PAPER1,
    SOURCE_SLOT_KEY_PAPER2,
    SOURCE_SLOT_PAPER1,
    SOURCE_SLOT_PAPER2,
    SOURCE_SLOT_SYLLABUS,
)
from app.jee_advanced.source_lifecycle import register_discovery_sources
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    SourceSlotDescriptor,
    _find_slot_source,
)
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import SourceIngestionMethod, SourceRevisionStatus
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.security import FetchedSource, SourceFetchError, UnsafeSourceUrl
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


class UntrustedOriginError(SourceFetchError):
    """Raised when a URL is not the approved official JEE Advanced HTTPS origin."""


class SlotLifecycleStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    FETCH_BLOCKED = "FETCH_BLOCKED"
    STAGED = "STAGED"
    STAGED_WITH_ISSUES = "STAGED_WITH_ISSUES"
    IDENTITY_REVIEW_PENDING = "IDENTITY_REVIEW_PENDING"
    CURATOR_PENDING = "CURATOR_PENDING"
    RIGHTS_REVIEW_PENDING = "RIGHTS_REVIEW_PENDING"


MANUAL_UPLOAD_INSTRUCTION = (
    "Place the original PDF bytes under SOURCE_STORAGE_DIR via "
    "SourceIntelligenceService.ingest_upload (PDF method) after Founder confirms "
    "rights; never commit PDFs to Git."
)

FOUNDER_LOCAL_STAGING_COMMAND = (
    "cd backend && python ../scripts/ingestion/jee_advanced_2026_private_stage.py"
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
    page_count: int | None = None
    retrieved_at: str | None = None
    storage_digest_verified: bool = False
    mime_verified: bool = False
    blocked_reason: str | None = None


def assert_official_jeeadv_https_url(url: str) -> None:
    """STG-01: only https://jeeadv.ac.in (exact host, no lookalikes)."""

    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: official sources require HTTPS")
    host = (parsed.hostname or "").rstrip(".").lower()
    if host != JEE_ADVANCED_OFFICIAL_HOST:
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: host is not jeeadv.ac.in")


class OfficialHostBoundFetcher:
    """Wrap Day3 fetcher; validate initial and final URL before returning bytes."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def fetch(self, url: str) -> FetchedSource:
        assert_official_jeeadv_https_url(url)
        transport = getattr(self._inner, "transport", None)
        if transport is not None:
            self._assert_mock_redirect_chain_official(url, transport)
        result: FetchedSource = self._inner.fetch(url)
        assert_official_jeeadv_https_url(result.final_url)
        return result

    def _assert_mock_redirect_chain_official(
        self,
        url: str,
        transport: httpx.BaseTransport,
    ) -> None:
        """Reject cross-host redirects before inner fetch stores bytes (tests + staging)."""

        current = url
        client = httpx.Client(
            follow_redirects=False,
            timeout=getattr(self._inner, "timeout_seconds", 5.0),
            transport=transport,
            headers={"user-agent": "Eduvijna-Source-Intelligence/1.0"},
            trust_env=False,
        )
        try:
            for _ in range(getattr(self._inner, "max_redirects", 3) + 1):
                assert_official_jeeadv_https_url(current)
                try:
                    response = client.get(current)
                except httpx.HTTPError:
                    return
                if response.status_code not in {301, 302, 303, 307, 308}:
                    return
                location = response.headers.get("location")
                if not location:
                    return
                current = urljoin(current, location)
        finally:
            client.close()


def export_src01_manifest() -> list[dict[str, Any]]:
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


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def pdf_page_count(content: bytes) -> int | None:
    if not pdf_magic_valid(content):
        return None
    try:
        reader = PdfReader(io.BytesIO(content))
        return len(reader.pages)
    except Exception:
        return None


def _path_signals(path: str) -> dict[str, bool]:
    lowered = path.lower()
    return {
        "p1_question": "p1_english" in lowered,
        "p2_question": "p2_english" in lowered,
        "p1_key": "p1_solutions" in lowered,
        "p2_key": "p2_solutions" in lowered,
        "syllabus": "syllabus" in lowered,
        "brochure": "ibenglish" in lowered,
        "solutions": "solutions" in lowered,
        "year_2027": "2027" in lowered,
    }


def _url_path_signals(final_url: str | None) -> dict[str, bool]:
    if not final_url:
        return {}
    return _path_signals(urlsplit(final_url).path)


def _filename_signals(filename: str | None) -> dict[str, bool]:
    if not filename:
        return {}
    return _path_signals(filename)


def _content_signals(content: bytes) -> dict[str, bool]:
    sample = content[:12_000].lower()
    return {
        "year_2027": b"2027" in sample and b"2026" not in sample[:4000],
        "p1_question": b"p1_english" in sample or b"paper 1" in sample,
        "p2_question": b"p2_english" in sample or b"paper 2" in sample,
        "solutions": b"solutions" in sample or b"answer key" in sample,
    }


def _slot_url_expectations(slot_id: str) -> dict[str, bool]:
    if slot_id == SOURCE_SLOT_PAPER1:
        return {"p1_question": True}
    if slot_id == SOURCE_SLOT_PAPER2:
        return {"p2_question": True}
    if slot_id == SOURCE_SLOT_KEY_PAPER1:
        return {"p1_key": True, "solutions": True}
    if slot_id == SOURCE_SLOT_KEY_PAPER2:
        return {"p2_key": True, "solutions": True}
    if slot_id == SOURCE_SLOT_SYLLABUS:
        return {"syllabus": True}
    if slot_id == SOURCE_SLOT_BROCHURE:
        return {"brochure": True}
    return {}


def slot_identity_issue_codes(
    slot_id: str,
    *,
    final_url: str | None,
    filename: str | None,
    content: bytes,
) -> tuple[str, ...]:
    """STG-02: independent URL, filename and content checks (no combined-hint cancellation)."""

    issues: list[str] = []
    if not pdf_magic_valid(content):
        issues.append("staged_content_not_pdf")
    pages = pdf_page_count(content)
    if pdf_magic_valid(content) and pages is None:
        issues.append("pdf_not_parseable")
    if pages == 0:
        issues.append("IDENTITY_REVIEW_PENDING")

    url_sig = _url_path_signals(final_url)
    file_sig = _filename_signals(filename)
    content_sig = _content_signals(content)
    expected = _slot_url_expectations(slot_id)

    for key, required in expected.items():
        if required and not url_sig.get(key):
            issues.append(f"url_slot_{key}_missing")
        if required and url_sig.get("year_2027"):
            issues.append("wrong_exam_year_in_url")

    for key, required in expected.items():
        if required and filename and not file_sig.get(key):
            issues.append(f"filename_slot_{key}_missing")

    if url_sig.get("p1_question") and url_sig.get("p2_question"):
        issues.append("url_conflicting_paper_tokens")
    if file_sig.get("p1_question") and file_sig.get("p2_question"):
        issues.append("filename_conflicting_paper_tokens")
    if url_sig.get("p1_question") and file_sig.get("p2_question"):
        issues.append("filename_url_identity_conflict")
    if url_sig.get("p2_question") and file_sig.get("p1_question"):
        issues.append("filename_url_identity_conflict")

    if slot_id in {SOURCE_SLOT_PAPER1, SOURCE_SLOT_PAPER2} and url_sig.get("solutions"):
        issues.append("question_paper_answer_key_mixup")
    if slot_id in {SOURCE_SLOT_KEY_PAPER1, SOURCE_SLOT_KEY_PAPER2}:
        if url_sig.get("p1_question") or url_sig.get("p2_question"):
            if not url_sig.get("solutions"):
                issues.append("answer_key_question_paper_mixup")

    if content_sig.get("year_2027"):
        issues.append("wrong_exam_year_in_content")

    if slot_id == SOURCE_SLOT_PAPER1 and content_sig.get("p2_question") and not content_sig.get(
        "p1_question"
    ):
        issues.append("content_paper_slot_mismatch")
    if slot_id == SOURCE_SLOT_PAPER2 and content_sig.get("p1_question") and not content_sig.get(
        "p2_question"
    ):
        issues.append("content_paper_slot_mismatch")

    return tuple(dict.fromkeys(issues))


def verify_response_pdf_mime(content_type: str | None) -> tuple[str, ...]:
    if not content_type:
        return ("missing_response_mime",)
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered not in {"application/pdf", "application/x-pdf"}:
        return ("response_mime_not_pdf",)
    return ()


def _sync_rights_metadata(source: Source) -> None:
    """STG-04: keep metadata aligned with canonical copyright_classification."""

    source.metadata_json = {
        **(source.metadata_json or {}),
        "copyright_classification": source.copyright_classification,
        "rights_review_status": SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
        "human_rights_disposition": None,
    }


def _ensure_slot_source(
    session: Session,
    service: SourceIntelligenceService,
    slot: SourceSlotDescriptor,
) -> Source:
    existing = _find_slot_source(session, slot.slot_id)
    if existing is not None:
        if existing.copyright_classification != COPYRIGHT_RIGHTS_RESERVED_REVIEW:
            existing.copyright_classification = COPYRIGHT_RIGHTS_RESERVED_REVIEW
            _sync_rights_metadata(existing)
            session.flush()
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
            "copyright_classification": COPYRIGHT_RIGHTS_RESERVED_REVIEW,
            "rights_review_status": SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            "lifecycle_status": SlotLifecycleStatus.DISCOVERED.value,
            "direct_pdf_url": slot.discovery_url,
            "staged_bytes_authoritative": False,
            "human_rights_disposition": None,
        },
    )
    source = service.register_source(
        payload,
        actor_id="source-ingest-staging",
        request_id=f"src-register-{slot.slot_id}",
    )
    _sync_rights_metadata(source)
    session.flush()
    return source


def _blocked_report(
    slot: SourceSlotDescriptor,
    *,
    source_id: str | None,
    issue_codes: tuple[str, ...],
    blocked_reason: str,
    discovery_url: str | None,
) -> SlotStagingReport:
    return SlotStagingReport(
        slot_id=slot.slot_id,
        lifecycle_status=SlotLifecycleStatus.FETCH_BLOCKED.value,
        discovery_url=discovery_url,
        final_url=None,
        sha256=None,
        byte_size=None,
        content_type=None,
        source_id=source_id,
        revision_id=None,
        rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
        curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
        issue_codes=issue_codes,
        pdf_magic_valid=False,
        blocked_reason=blocked_reason,
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
        return _blocked_report(
            slot,
            source_id=None,
            issue_codes=("missing_direct_pdf_url",),
            blocked_reason="missing_direct_pdf_url",
            discovery_url=None,
        )

    try:
        assert_official_jeeadv_https_url(slot.discovery_url)
    except UntrustedOriginError:
        return _blocked_report(
            slot,
            source_id=None,
            issue_codes=("UNTRUSTED_ORIGIN",),
            blocked_reason="UNTRUSTED_ORIGIN",
            discovery_url=slot.discovery_url,
        )

    source = _ensure_slot_source(session, service, slot)
    bound_fetcher = OfficialHostBoundFetcher(service.fetcher)
    try:
        fetched = bound_fetcher.fetch(slot.discovery_url)
    except UntrustedOriginError:
        return _blocked_report(
            slot,
            source_id=str(source.id),
            issue_codes=("UNTRUSTED_ORIGIN",),
            blocked_reason="UNTRUSTED_ORIGIN",
            discovery_url=slot.discovery_url,
        )
    except (SourceFetchError, UnsafeSourceUrl):
        return _blocked_report(
            slot,
            source_id=str(source.id),
            issue_codes=("FETCH_BLOCKED",),
            blocked_reason="FETCH_BLOCKED",
            discovery_url=slot.discovery_url,
        )

    mime_issues = verify_response_pdf_mime(fetched.content_type)
    if mime_issues:
        return _blocked_report(
            slot,
            source_id=str(source.id),
            issue_codes=mime_issues,
            blocked_reason=mime_issues[0],
            discovery_url=slot.discovery_url,
        )

    try:
        revision = service.ingest_upload(
            str(source.id),
            method=SourceIngestionMethod.PDF,
            content=fetched.content,
            filename=fetched.filename,
            actor_id=actor_id,
            request_id=request_id or f"src-ingest-{slot.slot_id}",
        )
    except (SourceFetchError, UnsafeSourceUrl, ValueError):
        return _blocked_report(
            slot,
            source_id=str(source.id),
            issue_codes=("FETCH_BLOCKED",),
            blocked_reason="FETCH_BLOCKED",
            discovery_url=slot.discovery_url,
        )

    meta = dict(revision.metadata_json or {})
    meta["requested_url"] = slot.discovery_url
    meta["final_url"] = fetched.final_url
    revision.metadata_json = meta
    session.flush()

    if not revision.storage_path:
        return SlotStagingReport(
            slot_id=slot.slot_id,
            lifecycle_status=SlotLifecycleStatus.STAGED_WITH_ISSUES.value,
            discovery_url=slot.discovery_url,
            final_url=fetched.final_url,
            sha256=revision.checksum,
            byte_size=revision.byte_size,
            content_type=fetched.content_type,
            source_id=str(source.id),
            revision_id=str(revision.id),
            rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
            issue_codes=("staged_storage_path_missing",),
            pdf_magic_valid=False,
            blocked_reason="staged_storage_path_missing",
        )

    content = service.storage.read(revision.storage_path)
    digest_verified = _sha256_bytes(content) == revision.checksum
    identity_issues: tuple[str, ...] = ()
    if not digest_verified:
        identity_issues = (*identity_issues, "stored_checksum_mismatch")
    identity_issues = (
        *identity_issues,
        *verify_response_pdf_mime(revision.content_type),
        *slot_identity_issue_codes(
            slot.slot_id,
            final_url=fetched.final_url,
            filename=revision.original_filename,
            content=content,
        ),
    )
    identity_issues = tuple(dict.fromkeys(identity_issues))
    pages = pdf_page_count(content)
    if "IDENTITY_REVIEW_PENDING" in identity_issues:
        lifecycle = SlotLifecycleStatus.IDENTITY_REVIEW_PENDING.value
    elif identity_issues:
        lifecycle = SlotLifecycleStatus.STAGED_WITH_ISSUES.value
    else:
        lifecycle = SlotLifecycleStatus.STAGED.value

    retrieved_at: str | None = None
    if revision.retrieved_at is not None:
        retrieved_at = revision.retrieved_at.isoformat()

    return SlotStagingReport(
        slot_id=slot.slot_id,
        lifecycle_status=lifecycle,
        discovery_url=slot.discovery_url,
        final_url=fetched.final_url,
        sha256=revision.checksum if digest_verified else _sha256_bytes(content),
        byte_size=len(content),
        content_type=fetched.content_type,
        source_id=str(source.id),
        revision_id=str(revision.id),
        rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
        curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
        issue_codes=identity_issues,
        pdf_magic_valid=pdf_magic_valid(content),
        page_count=pages,
        retrieved_at=retrieved_at,
        storage_digest_verified=digest_verified,
        mime_verified="response_mime_not_pdf" not in identity_issues,
    )


def stage_all_official_slots_private(
    session: Session,
    storage: LocalSourceStorage,
) -> list[SlotStagingReport]:
    register_discovery_sources(session)
    service = SourceIntelligenceService(session, storage=storage)
    return [stage_official_slot(session, service, slot) for slot in JEE_ADVANCED_2026_SOURCE_SLOTS]


def build_redacted_inventory(reports: list[SlotStagingReport]) -> dict[str, Any]:
    return {
        "reference_evidence_ready": False,
        "curator_approval_performed": False,
        "manual_upload_fallback": MANUAL_UPLOAD_INSTRUCTION,
        "founder_local_repro_command": FOUNDER_LOCAL_STAGING_COMMAND,
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
                "page_count": report.page_count,
                "retrieved_at": report.retrieved_at,
                "storage_digest_verified": report.storage_digest_verified,
                "mime_verified": report.mime_verified,
                "blocked_reason": report.blocked_reason,
                "redacted": True,
            }
            for report in reports
        ],
    }


def build_provenance_inventory_from_session(
    session: Session,
    storage: LocalSourceStorage,
) -> dict[str, Any]:
    """STG-03: six-slot provenance from actual DB + private storage (redacted)."""

    service = SourceIntelligenceService(session, storage=storage)
    reports: list[SlotStagingReport] = []
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        source = _find_slot_source(session, slot.slot_id)
        revision = latest_staged_revision(session, slot.slot_id)
        if source is None or revision is None or not revision.storage_path:
            reports.append(
                SlotStagingReport(
                    slot_id=slot.slot_id,
                    lifecycle_status=SlotLifecycleStatus.DISCOVERED.value,
                    discovery_url=slot.discovery_url,
                    final_url=None,
                    sha256=None,
                    byte_size=None,
                    content_type=None,
                    source_id=str(source.id) if source else None,
                    revision_id=str(revision.id) if revision else None,
                    rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
                    curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
                    issue_codes=(),
                    pdf_magic_valid=False,
                    blocked_reason="not_staged_in_this_environment",
                )
            )
            continue
        content = service.storage.read(revision.storage_path)
        digest = _sha256_bytes(content)
        digest_verified = digest == revision.checksum
        meta = revision.metadata_json or {}
        identity_issues = slot_identity_issue_codes(
            slot.slot_id,
            final_url=str(meta.get("final_url") or source.url),
            filename=revision.original_filename,
            content=content,
        )
        if not digest_verified:
            identity_issues = (*identity_issues, "stored_checksum_mismatch")
        lifecycle = (
            SlotLifecycleStatus.STAGED_WITH_ISSUES.value
            if identity_issues
            else SlotLifecycleStatus.STAGED.value
        )
        retrieved_at = (
            revision.retrieved_at.isoformat() if revision.retrieved_at is not None else None
        )
        reports.append(
            SlotStagingReport(
                slot_id=slot.slot_id,
                lifecycle_status=lifecycle,
                discovery_url=source.url,
                final_url=str(meta.get("final_url") or source.url),
                sha256=digest if digest_verified else revision.checksum,
                byte_size=len(content),
                content_type=revision.content_type,
                source_id=str(source.id),
                revision_id=str(revision.id),
                rights_status=str(
                    (source.metadata_json or {}).get("rights_review_status")
                    or SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value
                ),
                curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
                issue_codes=identity_issues,
                pdf_magic_valid=pdf_magic_valid(content),
                page_count=pdf_page_count(content),
                retrieved_at=retrieved_at,
                storage_digest_verified=digest_verified,
                mime_verified=revision.content_type.lower().startswith("application/pdf"),
            )
        )
    inventory = build_redacted_inventory(reports)
    inventory["provenance_reproduced_in_builder"] = False
    inventory["provenance_note"] = (
        "Rebuild with founder_local_repro_command on Founder machine; "
        "do not treat prior builder hashes as freshly verified if not reproduced."
    )
    return inventory


def curator_handback_pending_actions() -> tuple[str, ...]:
    return (
        "Confirm rights_reserved_review_required for redistribution inside Eduvijna.",
        "Record explicit human_rights_disposition after legal review (separate from staging).",
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