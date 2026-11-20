"""Private JEE Advanced 2026 six-slot URL discovery and staging (SRC/STG; no curator approval)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.jee_advanced.constants import (
    BROCHURE_DISCOVERY_URL_ALTERNATE,
    BROCHURE_DISCOVERY_URL_PRIMARY,
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
from app.source_intelligence.security import (
    FetchedSource,
    SourceFetchError,
    SourceUrlFetcher,
    UnsafeSourceUrl,
)
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


class UntrustedOriginError(SourceFetchError):
    """Raised when a URL is not the approved official JEE Advanced HTTPS origin."""


class SlotLifecycleStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    FETCH_BLOCKED = "FETCH_BLOCKED"
    NOT_STAGED_HERE = "NOT_STAGED_HERE"
    STAGED = "STAGED"
    STAGED_WITH_ISSUES = "STAGED_WITH_ISSUES"
    IDENTITY_REVIEW_PENDING = "IDENTITY_REVIEW_PENDING"
    TRUSTED_REVISION_IMMUTABLE = "TRUSTED_REVISION_IMMUTABLE"
    CURATOR_PENDING = "CURATOR_PENDING"
    RIGHTS_REVIEW_PENDING = "RIGHTS_REVIEW_PENDING"


_PROTECTED_REVISION_STATUSES = frozenset(
    {
        SourceRevisionStatus.APPROVED.value,
        SourceRevisionStatus.ACTIVE.value,
        SourceRevisionStatus.SUPERSEDED.value,
    }
)


def _revision_protected_from_staging_mutation(revision: SourceRevision) -> bool:
    return revision.status in _PROTECTED_REVISION_STATUSES


def _find_protected_identity_revision(
    session: Session,
    source: Source,
    content: bytes,
) -> SourceRevision | None:
    """STG-43-01: read-only duplicate lookup before Day3 ingest (avoids restore path)."""

    checksum = _sha256_bytes(content)
    snapshot = SourceIntelligenceService._source_snapshot(source)
    snapshot_checksum = SourceIntelligenceService._snapshot_checksum(snapshot)
    with session.no_autoflush:
        return session.scalar(
            select(SourceRevision).where(
                SourceRevision.source_id == source.id,
                SourceRevision.checksum == checksum,
                SourceRevision.source_snapshot_checksum == snapshot_checksum,
                SourceRevision.status.in_(_PROTECTED_REVISION_STATUSES),
            )
        )


def _trusted_revision_immutable_report(
    slot: SourceSlotDescriptor,
    source: Source,
    revision: SourceRevision,
    *,
    fetched: FetchedSource | None = None,
) -> SlotStagingReport:
    meta = source.metadata_json or {}
    rev_meta = revision.metadata_json or {}
    return SlotStagingReport(
        slot_id=slot.slot_id,
        lifecycle_status=SlotLifecycleStatus.TRUSTED_REVISION_IMMUTABLE.value,
        discovery_url=slot.discovery_url,
        final_url=rev_meta.get("final_url"),
        sha256=revision.checksum,
        byte_size=revision.byte_size,
        content_type=(
            rev_meta.get("fetch_response_content_type")
            or (fetched.content_type if fetched else None)
        ),
        source_id=str(source.id),
        revision_id=str(revision.id),
        rights_status=str(
            meta.get("rights_review_status")
            or SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value
        ),
        curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
        issue_codes=(
            "EXISTING_TRUSTED_REVISION_READ_ONLY",
            "TRUSTED_REVISION_IMMUTABLE",
        ),
        pdf_magic_valid=pdf_magic_valid(
            fetched.content if fetched is not None else b"%PDF"
        ),
        observed_final_url=str(rev_meta.get("final_url"))
        if rev_meta.get("final_url")
        else (fetched.final_url if fetched else None),
        fetch_response_content_type=rev_meta.get("fetch_response_content_type")
        or (fetched.content_type if fetched else None),
        normalized_revision_content_type=revision.content_type,
        blocked_reason="EXISTING_TRUSTED_REVISION_READ_ONLY",
    )


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
    observed_final_url: str | None = None
    page_count: int | None = None
    retrieved_at: str | None = None
    storage_digest_verified: bool = False
    mime_verified: bool = False
    blocked_reason: str | None = None
    fetch_response_content_type: str | None = None
    normalized_revision_content_type: str | None = None
    storage_byte_size_verified: bool = False


def assert_official_jeeadv_https_url(url: str) -> None:
    """STG-41-01: exact https://jeeadv.ac.in on port 443 only."""

    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: official sources require HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: embedded credentials forbidden")
    host = (parsed.hostname or "").rstrip(".").lower()
    if host != JEE_ADVANCED_OFFICIAL_HOST:
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: host is not jeeadv.ac.in")
    port = parsed.port or 443
    if port != 443:
        raise UntrustedOriginError("UNTRUSTED_ORIGIN: official sources require port 443")


def staging_url_fetcher(service: SourceIntelligenceService) -> SourceUrlFetcher:
    """Build a fetcher with per-hop official-host validation for staging."""

    inner = service.fetcher
    settings = get_settings()
    return SourceUrlFetcher(
        timeout_seconds=settings.source_url_timeout_seconds,
        max_bytes=settings.source_max_bytes,
        max_redirects=settings.source_max_redirects,
        resolver=inner.resolver,
        transport=inner.transport,
        connection_factory=getattr(inner, "connection_factory", None),
        pre_hop_url_validator=assert_official_jeeadv_https_url,
    )


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
        "year_2024": "2024" in lowered,
    }


def _url_path_signals(final_url: str | None) -> dict[str, bool]:
    if not final_url:
        return {}
    return _path_signals(urlsplit(final_url).path)


def _filename_signals(filename: str | None) -> dict[str, bool]:
    if not filename:
        return {}
    return _path_signals(filename)


def _pdf_parsed_content_signals(content: bytes, *, max_pages: int = 8) -> dict[str, Any]:
    """Parse PDF text/metadata for identity evidence (STG-41-03)."""

    signals: dict[str, Any] = {
        "parseable": False,
        "year_2026": False,
        "year_2025": False,
        "year_2024": False,
        "year_2027": False,
        "p1_question": False,
        "p2_question": False,
        "p1_key": False,
        "p2_key": False,
        "solutions": False,
        "brochure": False,
        "syllabus": False,
        "page_count": 0,
    }
    if not pdf_magic_valid(content):
        return signals
    try:
        reader = PdfReader(io.BytesIO(content))
        signals["page_count"] = len(reader.pages)
        if signals["page_count"] <= 0:
            return signals
        signals["parseable"] = True
        chunks: list[str] = []
        if reader.metadata:
            chunks.extend(
                str(reader.metadata.get(key) or "")
                for key in ("/Title", "/Subject", "/Keywords")
            )
        for page in reader.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
        text = " ".join(chunks).lower()
        signals["year_2026"] = "2026" in text
        signals["year_2025"] = "2025" in text
        signals["year_2024"] = "2024" in text
        signals["year_2027"] = "2027" in text
        signals["p1_question"] = "paper 1" in text or "paper1" in text or "p1_english" in text
        signals["p2_question"] = "paper 2" in text or "paper2" in text or "p2_english" in text
        signals["p1_key"] = "p1_solutions" in text or "paper 1 solution" in text
        signals["p2_key"] = "p2_solutions" in text or "paper 2 solution" in text
        signals["solutions"] = "solution" in text or "answer key" in text
        signals["brochure"] = "information brochure" in text or "ibenglish" in text
        signals["syllabus"] = "syllabus" in text
    except Exception:
        signals["parseable"] = False
    return signals


def _slot_content_expectations(slot_id: str) -> dict[str, bool]:
    return _slot_url_expectations(slot_id)


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
    content_sig = _pdf_parsed_content_signals(content)
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

    if not content_sig.get("parseable"):
        issues.append("IDENTITY_REVIEW_PENDING")
    else:
        year_hits = sum(
            1
            for key in ("year_2026", "year_2025", "year_2024", "year_2027")
            if content_sig.get(key)
        )
        if year_hits > 1:
            issues.append("CONFLICTING_DOCUMENT_YEARS")
        elif content_sig.get("year_2027"):
            issues.append("wrong_exam_year_in_content")
        elif not content_sig.get("year_2026"):
            if content_sig.get("year_2025"):
                issues.append("WRONG_DOCUMENT_YEAR")
            else:
                issues.append("IDENTITY_REVIEW_PENDING")
        if content_sig.get("p1_question") and content_sig.get("p2_question"):
            issues.append("content_conflicting_paper_tokens")
        if content_sig.get("p1_question") and content_sig.get("p1_key"):
            issues.append("content_question_paper_answer_key_mixup")
        if content_sig.get("p2_question") and content_sig.get("p2_key"):
            issues.append("content_question_paper_answer_key_mixup")
        for key, required in _slot_content_expectations(slot_id).items():
            if required and not content_sig.get(key):
                issues.append(f"content_slot_{key}_missing")
        if slot_id == SOURCE_SLOT_PAPER1 and content_sig.get("p2_question") and not content_sig.get(
            "p1_question"
        ):
            issues.append("content_paper_slot_mismatch")
        if slot_id == SOURCE_SLOT_PAPER2 and content_sig.get("p1_question") and not content_sig.get(
            "p2_question"
        ):
            issues.append("content_paper_slot_mismatch")
        if slot_id in {SOURCE_SLOT_PAPER1, SOURCE_SLOT_PAPER2} and (
            content_sig.get("solutions")
            or content_sig.get("p1_key")
            or content_sig.get("p2_key")
        ):
            if slot_id == SOURCE_SLOT_PAPER1 and not content_sig.get("p1_key"):
                if content_sig.get("solutions") or content_sig.get("p2_key"):
                    issues.append("content_question_paper_answer_key_mixup")
            if slot_id == SOURCE_SLOT_PAPER2 and not content_sig.get("p2_key"):
                if content_sig.get("solutions") or content_sig.get("p1_key"):
                    issues.append("content_question_paper_answer_key_mixup")
        if slot_id in {SOURCE_SLOT_KEY_PAPER1, SOURCE_SLOT_KEY_PAPER2} and (
            content_sig.get("p1_question") or content_sig.get("p2_question")
        ):
            if not content_sig.get("solutions"):
                issues.append("content_answer_key_question_mixup")

    return tuple(dict.fromkeys(issues))


def verify_response_pdf_mime(content_type: str | None) -> tuple[str, ...]:
    if not content_type:
        return ("missing_response_mime",)
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered not in {"application/pdf", "application/x-pdf"}:
        return ("response_mime_not_pdf",)
    return ()


def _source_has_ingestion_failure_audit(session: Session, source_id: str) -> bool:
    """True when persisted source_ingestion_failed audit exists (STG-42-04)."""

    row = session.scalar(
        select(SourceAuditEvent.id)
        .where(
            SourceAuditEvent.source_id == source_id,
            SourceAuditEvent.event_type == "source_ingestion_failed",
        )
        .limit(1)
    )
    return row is not None


def _rights_conflicts_if_any(source: Source) -> tuple[str, ...]:
    """STG-41-02/42-03: detect inconsistent or incomplete rights without mutating."""

    meta = source.metadata_json or {}
    canonical = (source.copyright_classification or "").strip()
    meta_cc = str(meta.get("copyright_classification") or "").strip()
    rights_status = str(meta.get("rights_review_status") or "").strip()
    issues: list[str] = []
    if not canonical or not meta_cc:
        issues.append("RIGHTS_REVIEW_PENDING")
    elif meta_cc != canonical:
        issues.append("RIGHTS_METADATA_CONFLICT")
    if not rights_status:
        issues.append("RIGHTS_REVIEW_PENDING")
    return tuple(dict.fromkeys(issues))


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
    session.flush()
    return source


def _apply_fetch_provenance(
    revision: SourceRevision,
    *,
    slot: SourceSlotDescriptor,
    fetched: FetchedSource,
) -> None:
    """Persist immutable URL/MIME provenance; do not rewrite locked records."""

    if _revision_protected_from_staging_mutation(revision):
        return
    meta = dict(revision.metadata_json or {})
    if meta.get("fetch_provenance_locked"):
        return
    meta.update(
        {
            "requested_url": slot.discovery_url,
            "final_url": fetched.final_url,
            "fetch_response_content_type": fetched.content_type,
            "fetch_ingestion_method": "url_fetch",
            "normalized_upload_content_type": revision.content_type,
            "fetch_provenance_locked": True,
        }
    )
    revision.metadata_json = meta


def _slot_discovery_urls(slot: SourceSlotDescriptor) -> tuple[str, ...]:
    """Ordered official discovery URLs (brochure alternate per Issue #44)."""

    if slot.slot_id != SOURCE_SLOT_BROCHURE:
        return (slot.discovery_url,) if slot.discovery_url else ()
    ordered = [BROCHURE_DISCOVERY_URL_PRIMARY, BROCHURE_DISCOVERY_URL_ALTERNATE]
    if slot.discovery_url and slot.discovery_url not in ordered:
        ordered.insert(0, slot.discovery_url)
    return tuple(dict.fromkeys(url for url in ordered if url))


def _fetch_official_slot_bytes(
    fetcher: SourceUrlFetcher,
    slot: SourceSlotDescriptor,
) -> FetchedSource | None:
    """Try each discovery URL until one succeeds under the per-hop policy."""

    last_error: Exception | None = None
    for url in _slot_discovery_urls(slot):
        try:
            assert_official_jeeadv_https_url(url)
            return fetcher.fetch(url)
        except (UntrustedOriginError, SourceFetchError, UnsafeSourceUrl) as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return None


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
    rights_conflicts = _rights_conflicts_if_any(source)
    if rights_conflicts:
        meta = source.metadata_json or {}
        return SlotStagingReport(
            slot_id=slot.slot_id,
            lifecycle_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
            discovery_url=slot.discovery_url,
            final_url=None,
            sha256=None,
            byte_size=None,
            content_type=None,
            source_id=str(source.id),
            revision_id=None,
            rights_status=str(
                meta.get("rights_review_status")
                or SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value
            ),
            curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
            issue_codes=rights_conflicts,
            pdf_magic_valid=False,
            blocked_reason=rights_conflicts[0],
        )

    staging_fetcher = staging_url_fetcher(service)
    try:
        fetched = _fetch_official_slot_bytes(staging_fetcher, slot)
        if fetched is None:
            raise SourceFetchError("no discovery url configured")
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

    protected_preflight = _find_protected_identity_revision(session, source, fetched.content)
    if protected_preflight is not None:
        session.refresh(protected_preflight)
        return _trusted_revision_immutable_report(
            slot, source, protected_preflight, fetched=fetched
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

    if _revision_protected_from_staging_mutation(revision):
        session.refresh(revision)
        return _trusted_revision_immutable_report(
            slot, source, revision, fetched=fetched
        )

    _apply_fetch_provenance(revision, slot=slot, fetched=fetched)
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
    size_verified = len(content) == int(revision.byte_size or 0)
    identity_issues: tuple[str, ...] = ()
    if not digest_verified:
        identity_issues = (*identity_issues, "stored_checksum_mismatch")
    if not size_verified:
        identity_issues = (*identity_issues, "stored_byte_size_mismatch")
    identity_issues = (
        *identity_issues,
        *verify_response_pdf_mime(fetched.content_type),
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
    if (
        "WRONG_DOCUMENT_YEAR" in identity_issues
        or "CONFLICTING_DOCUMENT_YEARS" in identity_issues
    ):
        lifecycle = SlotLifecycleStatus.STAGED_WITH_ISSUES.value

    retrieved_at: str | None = None
    if revision.retrieved_at is not None:
        retrieved_at = revision.retrieved_at.isoformat()

    meta = source.metadata_json or {}
    return SlotStagingReport(
        slot_id=slot.slot_id,
        lifecycle_status=lifecycle,
        discovery_url=slot.discovery_url,
        final_url=fetched.final_url,
        observed_final_url=fetched.final_url,
        sha256=revision.checksum if digest_verified else _sha256_bytes(content),
        byte_size=len(content),
        content_type=fetched.content_type,
        fetch_response_content_type=fetched.content_type,
        normalized_revision_content_type=revision.content_type,
        source_id=str(source.id),
        revision_id=str(revision.id),
        rights_status=str(
            meta.get("rights_review_status")
            or SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value
        ),
        curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
        issue_codes=identity_issues,
        pdf_magic_valid=pdf_magic_valid(content),
        page_count=pages,
        retrieved_at=retrieved_at,
        storage_digest_verified=digest_verified,
        storage_byte_size_verified=size_verified,
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
                "final_url": report.observed_final_url,
                "observed_final_url": report.observed_final_url,
                "fetch_response_content_type": report.fetch_response_content_type,
                "normalized_revision_content_type": report.normalized_revision_content_type,
                "sha256": report.sha256,
                "byte_size": report.byte_size,
                "content_type": report.fetch_response_content_type or report.content_type,
                "source_id": report.source_id,
                "revision_id": report.revision_id,
                "rights_status": report.rights_status,
                "curator_status": report.curator_status,
                "issue_codes": list(report.issue_codes),
                "pdf_magic_valid": report.pdf_magic_valid,
                "page_count": report.page_count,
                "retrieved_at": report.retrieved_at,
                "storage_digest_verified": report.storage_digest_verified,
                "storage_byte_size_verified": report.storage_byte_size_verified,
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
            if source is None:
                blocked = None
                lifecycle = SlotLifecycleStatus.DISCOVERED.value
            elif revision is None or not revision.storage_path:
                if _source_has_ingestion_failure_audit(session, str(source.id)):
                    blocked = SlotLifecycleStatus.FETCH_BLOCKED.value
                    lifecycle = SlotLifecycleStatus.FETCH_BLOCKED.value
                else:
                    blocked = SlotLifecycleStatus.NOT_STAGED_HERE.value
                    lifecycle = SlotLifecycleStatus.NOT_STAGED_HERE.value
            else:
                blocked = SlotLifecycleStatus.NOT_STAGED_HERE.value
                lifecycle = SlotLifecycleStatus.NOT_STAGED_HERE.value
            reports.append(
                SlotStagingReport(
                    slot_id=slot.slot_id,
                    lifecycle_status=lifecycle,
                    discovery_url=slot.discovery_url,
                    final_url=None,
                    observed_final_url=None,
                    sha256=None,
                    byte_size=None,
                    content_type=None,
                    fetch_response_content_type=None,
                    normalized_revision_content_type=None,
                    source_id=str(source.id) if source else None,
                    revision_id=str(revision.id) if revision else None,
                    rights_status=SlotLifecycleStatus.RIGHTS_REVIEW_PENDING.value,
                    curator_status=SlotLifecycleStatus.CURATOR_PENDING.value,
                    issue_codes=(),
                    pdf_magic_valid=False,
                    blocked_reason=blocked,
                )
            )
            continue
        content = service.storage.read(revision.storage_path)
        digest = _sha256_bytes(content)
        digest_verified = digest == revision.checksum
        size_verified = len(content) == int(revision.byte_size or 0)
        meta = revision.metadata_json or {}
        observed_final = meta.get("final_url")
        identity_issues = slot_identity_issue_codes(
            slot.slot_id,
            final_url=str(observed_final) if observed_final else None,
            filename=revision.original_filename,
            content=content,
        )
        if not digest_verified:
            identity_issues = (*identity_issues, "stored_checksum_mismatch")
        if not size_verified:
            identity_issues = (*identity_issues, "stored_byte_size_mismatch")
        if "IDENTITY_REVIEW_PENDING" in identity_issues:
            lifecycle = SlotLifecycleStatus.IDENTITY_REVIEW_PENDING.value
        elif identity_issues:
            lifecycle = SlotLifecycleStatus.STAGED_WITH_ISSUES.value
        else:
            lifecycle = SlotLifecycleStatus.STAGED.value
        if (
            "WRONG_DOCUMENT_YEAR" in identity_issues
            or "CONFLICTING_DOCUMENT_YEARS" in identity_issues
        ):
            lifecycle = SlotLifecycleStatus.STAGED_WITH_ISSUES.value
        retrieved_at = (
            revision.retrieved_at.isoformat() if revision.retrieved_at is not None else None
        )
        fetch_mime = meta.get("fetch_response_content_type")
        reports.append(
            SlotStagingReport(
                slot_id=slot.slot_id,
                lifecycle_status=lifecycle,
                discovery_url=slot.discovery_url,
                final_url=str(observed_final) if observed_final else None,
                observed_final_url=str(observed_final) if observed_final else None,
                sha256=digest if digest_verified else revision.checksum,
                byte_size=len(content),
                content_type=str(fetch_mime) if fetch_mime else None,
                fetch_response_content_type=str(fetch_mime) if fetch_mime else None,
                normalized_revision_content_type=revision.content_type,
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
                storage_byte_size_verified=size_verified,
                mime_verified=(
                    bool(fetch_mime)
                    and str(fetch_mime).lower().startswith("application/pdf")
                ),
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