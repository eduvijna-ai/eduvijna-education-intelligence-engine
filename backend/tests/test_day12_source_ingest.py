"""D12-SOURCE-INGEST-01: discovery manifest and private staging guards (Issue #39)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.constants import OFFICIAL_DISCOVERY_URLS, VERSION_CANDIDATE_2027
from app.jee_advanced.core_test_fixtures import _simple_pdf_bytes
from app.jee_advanced.source_ingest_staging import (
    MANUAL_UPLOAD_INSTRUCTION,
    UntrustedOriginError,
    assert_no_curator_approval_events,
    assert_official_jeeadv_https_url,
    build_provenance_inventory_from_session,
    build_redacted_inventory,
    export_src01_manifest,
    slot_identity_issue_codes,
    stage_official_slot,
)
from app.jee_advanced.source_lifecycle import register_discovery_sources
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    SourceSlotDescriptor,
    _find_slot_source,
    reference_evidence_ready,
)
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import SourceRevisionStatus
from app.source_intelligence.security import (
    SourceUrlFetcher,
    UnsafeSourceUrl,
    validate_source_url,
)
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

_ISSUE_URLS = {
    "brochure_en_2026": "https://jeeadv.ac.in/documents/IBEnglish_2026.pdf",
    "syllabus_2026": "https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf",
    "paper1_en_2026": "https://jeeadv.ac.in/documents/p1_english.pdf",
    "paper2_en_2026": "https://jeeadv.ac.in/documents/p2_english.pdf",
    "key_paper1_final_2026": "https://jeeadv.ac.in/documents/p1_solutions_final.pdf",
    "key_paper2_final_2026": "https://jeeadv.ac.in/documents/p2_solutions_final.pdf",
}

_PUBLIC_RESOLVER = lambda _h: ["93.184.216.34"]  # noqa: E731


def _minimal_pdf(label: str = "slot") -> bytes:
    safe = label.replace("(", "[").replace(")", "]")
    return f"%PDF-1.4\n% {safe}\n%%EOF\n".encode()


def _slot_pdf(slot: SourceSlotDescriptor) -> bytes:
    if slot.slot_id.endswith("brochure"):
        return _simple_pdf_bytes("JEE Advanced information brochure 2026 IBEnglish")
    if "syllabus" in slot.slot_id:
        return _simple_pdf_bytes("JEE Advanced official syllabus 2026")
    if slot.slot_id.endswith("paper_1"):
        return _simple_pdf_bytes("JEE Advanced Paper 1 2026 p1_english")
    if slot.slot_id.endswith("paper_2"):
        return _simple_pdf_bytes("JEE Advanced Paper 2 2026 p2_english")
    if slot.slot_id.endswith("key_paper_1"):
        return _simple_pdf_bytes("Paper 1 final answer key 2026 p1_solutions")
    if slot.slot_id.endswith("key_paper_2"):
        return _simple_pdf_bytes("Paper 2 final answer key 2026 p2_solutions")
    return _simple_pdf_bytes(f"slot {slot.slot_id} 2026")


def _session(tmp_path: Path) -> tuple[Session, SourceIntelligenceService]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'ingest.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    storage = LocalSourceStorage(tmp_path / "private-sources")
    service = SourceIntelligenceService(session, storage=storage)
    return session, service


def _mock_fetcher(handlers: dict[str, bytes]) -> SourceUrlFetcher:
    def route(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, payload in handlers.items():
            if key in url:
                return httpx.Response(
                    200,
                    request=request,
                    headers={"content-type": "application/pdf"},
                    content=payload,
                )
        raise httpx.ConnectError("blocked", request=request)

    return SourceUrlFetcher(
        timeout_seconds=3,
        max_bytes=8_000_000,
        max_redirects=3,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(route),
    )


def test_src01_manifest_has_six_direct_pdf_urls() -> None:
    manifest = export_src01_manifest()
    assert len(manifest) == 6
    for row in manifest:
        assert row["direct_pdf_url"]
        assert "jeeadv.ac.in/documents/" in row["direct_pdf_url"]
        assert row["rights_review_status"] == "RIGHTS_REVIEW_PENDING"
        assert row["staged_bytes_known"] is False
    for key, url in _ISSUE_URLS.items():
        assert OFFICIAL_DISCOVERY_URLS[key] == url


def test_registry_slots_no_site_home_placeholder() -> None:
    for slot in JEE_ADVANCED_2026_SOURCE_SLOTS:
        assert slot.discovery_url
        assert slot.discovery_url != OFFICIAL_DISCOVERY_URLS["site_home"]
        assert "/documents/" in slot.discovery_url


def test_slot_identity_rejects_html_masquerade() -> None:
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p1_english.pdf",
        filename="p1_english.pdf",
        content=b"<html>not a pdf</html>",
    )
    assert "staged_content_not_pdf" in issues


def test_slot_identity_rejects_paper_swap() -> None:
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p2_english.pdf",
        filename="p2_english.pdf",
        content=_minimal_pdf("p2"),
    )
    assert "url_slot_p1_question_missing" in issues


def test_slot_identity_rejects_key_question_mixup() -> None:
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.key_paper_1",
        final_url="https://jeeadv.ac.in/documents/p1_english.pdf",
        filename="p1_english.pdf",
        content=_minimal_pdf("qp"),
    )
    assert "answer_key_question_paper_mixup" in issues


def test_untrusted_host_blocked_before_fetch() -> None:
    with pytest.raises(UnsafeSourceUrl):
        validate_source_url("http://127.0.0.1/private.pdf", resolver=_PUBLIC_RESOLVER)


def test_stg01_official_host_guard_rejects_attacker_domain() -> None:
    with pytest.raises(UntrustedOriginError):
        assert_official_jeeadv_https_url("https://attacker.example/documents/p1_english.pdf")


def test_stg01_off_host_staging_untrusted_origin_no_revision(tmp_path: Path) -> None:
    slot = JEE_ADVANCED_2026_SOURCE_SLOTS[2]
    hostile = replace(
        slot,
        discovery_url="https://attacker.example/documents/p1_english.pdf",
    )
    session, service = _session(tmp_path)
    try:
        report = stage_official_slot(session, service, hostile)
        assert report.revision_id is None
        assert "UNTRUSTED_ORIGIN" in report.issue_codes
        assert report.lifecycle_status == "FETCH_BLOCKED"
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg01_cross_host_redirect_blocked(tmp_path: Path) -> None:
    session, service = _session(tmp_path)
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            request=request,
            headers={"location": "https://evil.example/documents/payload.pdf"},
            content=b"",
        )

    service.fetcher = SourceUrlFetcher(
        timeout_seconds=2,
        max_bytes=4096,
        max_redirects=2,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(redirect),
    )
    try:
        report = stage_official_slot(session, service, slot)
        assert report.revision_id is None
        assert "UNTRUSTED_ORIGIN" in report.issue_codes
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg02_wrong_mime_not_staged(tmp_path: Path) -> None:
    session, service = _session(tmp_path)
    slot = JEE_ADVANCED_2026_SOURCE_SLOTS[0]

    def html_pdf_name(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html"},
            content=b"<html>not pdf</html>",
        )

    service.fetcher = SourceUrlFetcher(
        timeout_seconds=2,
        max_bytes=4096,
        max_redirects=0,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(html_pdf_name),
    )
    try:
        report = stage_official_slot(session, service, slot)
        assert report.revision_id is None
        assert "response_mime_not_pdf" in report.issue_codes
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg02_filename_url_p1_p2_conflict_detected() -> None:
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p2_english.pdf",
        filename="p1_english.pdf",
        content=_minimal_pdf("mixed"),
    )
    assert "filename_url_identity_conflict" in issues


def test_stg04_rights_review_pending_blocks_reference_ready(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher(
        {"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)}
    )
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        assert report.rights_status == "RIGHTS_REVIEW_PENDING"
        source = session.scalar(select(Source).where(Source.id == report.source_id))
        assert source is not None
        assert source.copyright_classification == "rights_reserved_review_required"
        meta = source.metadata_json or {}
        assert meta.get("copyright_classification") == source.copyright_classification
        assert meta.get("rights_review_status") == "RIGHTS_REVIEW_PENDING"
        assert reference_evidence_ready(session) is False
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_private_staging_never_approves_or_sets_reference_ready(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("syllabus"))
    handlers = {"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)}
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher(handlers)
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        assert report.sha256
        assert report.lifecycle_status in {
            "STAGED",
            "STAGED_WITH_ISSUES",
            "IDENTITY_REVIEW_PENDING",
        }
        assert report.curator_status == "CURATOR_PENDING"
        assert assert_no_curator_approval_events(session) == []
        assert reference_evidence_ready(session) is False
        forbidden = session.scalars(
            select(SourceAuditEvent).where(SourceAuditEvent.event_type == "source_approved")
        ).all()
        assert forbidden == []
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_fetch_blocked_reports_typed_status(tmp_path: Path) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("FETCH_BLOCKED synthetic", request=httpx.Request("GET", "http://x"))

    session, service = _session(tmp_path)
    service.fetcher = SourceUrlFetcher(
        timeout_seconds=1,
        max_bytes=4096,
        max_redirects=0,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(fail),
    )
    slot = JEE_ADVANCED_2026_SOURCE_SLOTS[0]
    try:
        report = stage_official_slot(session, service, slot)
        assert report.lifecycle_status == "FETCH_BLOCKED"
        assert "FETCH_BLOCKED" in report.issue_codes
        assert MANUAL_UPLOAD_INSTRUCTION
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_idempotent_staging_duplicate_bytes(tmp_path: Path) -> None:
    payload = _minimal_pdf("dup")
    handlers = {"/p1_english.pdf": payload, "/p2_english.pdf": payload}
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher(handlers)
    paper1 = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    try:
        first = stage_official_slot(session, service, paper1)
        second = stage_official_slot(session, service, paper1)
        session.commit()
        assert first.revision_id == second.revision_id
        assert first.sha256 == second.sha256
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_checksum_drift_creates_new_revision(tmp_path: Path) -> None:
    session, service = _session(tmp_path)
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_2"))

    def first(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "application/pdf"},
            content=_minimal_pdf("v1"),
        )

    service.fetcher = SourceUrlFetcher(
        timeout_seconds=2,
        max_bytes=4096,
        max_redirects=0,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(first),
    )
    try:
        r1 = stage_official_slot(session, service, slot)
        service.fetcher = SourceUrlFetcher(
            timeout_seconds=2,
            max_bytes=4096,
            max_redirects=0,
            resolver=_PUBLIC_RESOLVER,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    request=request,
                    headers={"content-type": "application/pdf"},
                    content=_minimal_pdf("v2-drift"),
                )
            ),
        )
        r2 = stage_official_slot(session, service, slot)
        session.commit()
        assert r1.sha256 != r2.sha256
        assert r1.revision_id != r2.revision_id
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stage_all_builds_redacted_inventory(tmp_path: Path) -> None:
    handlers = {
        slot.discovery_url.rsplit("/", 1)[-1]: _slot_pdf(slot)
        for slot in JEE_ADVANCED_2026_SOURCE_SLOTS
    }
    engine = create_database_engine(f"sqlite:///{tmp_path / 'all.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    storage = LocalSourceStorage(tmp_path / "all-private")
    service = SourceIntelligenceService(session, storage=storage)
    service.fetcher = _mock_fetcher(handlers)
    try:
        reports = [
            stage_official_slot(session, service, slot) for slot in JEE_ADVANCED_2026_SOURCE_SLOTS
        ]
        session.commit()
        inventory = build_redacted_inventory(reports)
        assert inventory["reference_evidence_ready"] is False
        assert inventory["curator_approval_performed"] is False
        assert len(inventory["slots"]) == 6
        for row in inventory["slots"]:
            assert row["sha256"]
            assert row["revision_id"]
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_synthetic_surrogate_not_treated_as_official_pass(tmp_path: Path) -> None:
    session, service = _session(tmp_path)
    slot = JEE_ADVANCED_2026_SOURCE_SLOTS[0]
    service.fetcher = _mock_fetcher(
        {"IBEnglish_2026.pdf": b"SYNTHETIC_NOT_PDF_SURROGATE"}
    )
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        assert report.pdf_magic_valid is False
        assert reference_evidence_ready(session) is False
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_2027_candidate_not_in_src01_manifest() -> None:
    manifest = export_src01_manifest()
    joined = json.dumps(manifest)
    assert VERSION_CANDIDATE_2027 not in joined
    assert "2027" not in joined


def test_stg41_pre_hop_blocks_evil_redirect_without_foreign_connection() -> None:
    """STG41-01: per-hop validator runs before each real-path connection attempt."""

    attempted_hosts: list[str] = []

    class _RedirectResponse:
        status = 302

        def getheader(self, name: str, default: str | None = None) -> str | None:
            if name.lower() == "location":
                return "https://evil.example/documents/payload.pdf"
            return default

    class _Connection:
        def request(self, *_: object, **__: object) -> None:
            return None

        def getresponse(self) -> _RedirectResponse:
            return _RedirectResponse()

        def close(self) -> None:
            return None

    def factory(
        _scheme: str,
        hostname: str,
        _port: int,
        _timeout: float,
        _pinned: str,
    ) -> _Connection:
        attempted_hosts.append(hostname)
        return _Connection()

    fetcher = SourceUrlFetcher(
        timeout_seconds=2,
        max_bytes=4096,
        max_redirects=2,
        resolver=_PUBLIC_RESOLVER,
        transport=None,
        connection_factory=factory,
        pre_hop_url_validator=assert_official_jeeadv_https_url,
    )
    with pytest.raises(UntrustedOriginError):
        fetcher.fetch("https://jeeadv.ac.in/documents/redirect-entry.pdf")
    assert attempted_hosts == ["jeeadv.ac.in"]


def test_stg41_rerun_staging_preserves_human_rights_across_sessions(tmp_path: Path) -> None:
    """STG41-02: re-staging must not reset existing human rights metadata."""

    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)
    db_path = tmp_path / "rights.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / "rights-private")
    session = Session(engine)
    service = SourceIntelligenceService(session, storage=storage)
    service.fetcher = _mock_fetcher({"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)})
    try:
        stage_official_slot(session, service, slot)
        source = _find_slot_source(session, slot.slot_id)
        assert source is not None
        source.copyright_classification = "founder_reviewed_reserved"
        meta = dict(source.metadata_json or {})
        meta["copyright_classification"] = "founder_reviewed_reserved"
        meta["human_rights_disposition"] = "internal_use_only_pending_curator"
        meta["rights_review_status"] = "HUMAN_REVIEW_RECORDED"
        source.metadata_json = meta
        session.commit()
        rights_snapshot = {
            "copyright_classification": source.copyright_classification,
            "human_rights_disposition": meta.get("human_rights_disposition"),
            "rights_review_status": meta.get("rights_review_status"),
        }
    finally:
        session.close()
        create_database_engine.cache_clear()

    engine2 = create_database_engine(f"sqlite:///{db_path}")
    session2 = Session(engine2)
    service2 = SourceIntelligenceService(session2, storage=storage)
    service2.fetcher = _mock_fetcher({"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)})
    try:
        stage_official_slot(session2, service2, slot)
        session2.commit()
        source2 = _find_slot_source(session2, slot.slot_id)
        assert source2 is not None
        assert source2.copyright_classification == rights_snapshot["copyright_classification"]
        meta2 = source2.metadata_json or {}
        assert meta2.get("human_rights_disposition") == rights_snapshot["human_rights_disposition"]
        assert meta2.get("rights_review_status") == rights_snapshot["rights_review_status"]
        assert meta2.get("copyright_classification") == rights_snapshot["copyright_classification"]
    finally:
        session2.close()
        create_database_engine.cache_clear()


def test_stg41_parseable_wrong_paper_content_flagged() -> None:
    payload = _simple_pdf_bytes("JEE Advanced Paper 2 2026 p2_english")
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p1_english.pdf",
        filename="p1_english.pdf",
        content=payload,
    )
    assert "content_paper_slot_mismatch" in issues or "content_slot_p1_question_missing" in issues


def test_stg41_provenance_inventory_truthful_fields(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)
    db_path = tmp_path / "prov.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / "prov-private")
    session = Session(engine)
    service = SourceIntelligenceService(session, storage=storage)
    service.fetcher = _mock_fetcher({"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)})
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        inventory = build_provenance_inventory_from_session(session, storage)
        row = next(r for r in inventory["slots"] if r["slot_id"] == slot.slot_id)
        assert row["discovery_url"] == slot.discovery_url
        assert row["observed_final_url"] == report.observed_final_url
        assert row["fetch_response_content_type"] == "application/pdf"
        assert row["normalized_revision_content_type"] == "application/pdf"
        assert row["sha256"] == report.sha256
        assert row["storage_digest_verified"] is True
        assert row["storage_byte_size_verified"] is True
        sha_first = row["sha256"]
    finally:
        session.close()
        create_database_engine.cache_clear()

    engine2 = create_database_engine(f"sqlite:///{db_path}")
    session2 = Session(engine2)
    try:
        inventory2 = build_provenance_inventory_from_session(session2, storage)
        row2 = next(r for r in inventory2["slots"] if r["slot_id"] == slot.slot_id)
        assert row2["sha256"] == sha_first
        assert row2["observed_final_url"] is not None
        assert "source.url" not in (row2["discovery_url"] or "")
    finally:
        session2.close()
        create_database_engine.cache_clear()


def test_stg42_approved_revision_unchanged_on_duplicate_staging(tmp_path: Path) -> None:
    """STG42-01: dedup must not mutate APPROVED revision metadata (missing provenance lock)."""

    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    db_path = tmp_path / "immutable.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / "immutable-private")
    session = Session(engine)
    service = SourceIntelligenceService(session, storage=storage)
    payload = _slot_pdf(slot)
    service.fetcher = _mock_fetcher({"/p1_english.pdf": payload})
    try:
        first = stage_official_slot(session, service, slot)
        session.commit()
        revision = session.get(SourceRevision, first.revision_id)
        assert revision is not None
        preserved_meta = {"curator_binding": "test-only", "no_fetch_provenance_lock": True}
        revision.metadata_json = preserved_meta
        revision.status = SourceRevisionStatus.APPROVED.value
        revision.approved_by = "human-curator-test"
        revision.approval_fingerprint = "fingerprint-keep-001"
        session.commit()
        rev_id = str(revision.id)
        fingerprint = revision.approval_fingerprint
    finally:
        session.close()
        create_database_engine.cache_clear()

    engine2 = create_database_engine(f"sqlite:///{db_path}")
    session2 = Session(engine2)
    service2 = SourceIntelligenceService(session2, storage=storage)
    service2.fetcher = _mock_fetcher({"/p1_english.pdf": payload})
    try:
        second = stage_official_slot(session2, service2, slot)
        session2.commit()
        assert second.lifecycle_status == "TRUSTED_REVISION_IMMUTABLE"
        assert "TRUSTED_REVISION_IMMUTABLE" in second.issue_codes
        assert "EXISTING_TRUSTED_REVISION_READ_ONLY" in second.issue_codes
        revision2 = session2.get(SourceRevision, rev_id)
        assert revision2 is not None
        assert revision2.metadata_json == preserved_meta
        assert revision2.approval_fingerprint == fingerprint
        assert revision2.status == SourceRevisionStatus.APPROVED.value
    finally:
        session2.close()
        create_database_engine.cache_clear()


def test_stg42_parseable_2025_paper_rejected() -> None:
    payload = _simple_pdf_bytes("JEE Advanced Paper 1 2025 p1_english")
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p1_english.pdf",
        filename="p1_english.pdf",
        content=payload,
    )
    assert "WRONG_DOCUMENT_YEAR" in issues


def test_stg42_staging_2025_pdf_not_clean_staged(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    session, service = _session(tmp_path)
    wrong_year = _simple_pdf_bytes("JEE Advanced Paper 1 2025 p1_english")
    service.fetcher = _mock_fetcher({"/p1_english.pdf": wrong_year})
    try:
        report = stage_official_slot(session, service, slot)
        assert "WRONG_DOCUMENT_YEAR" in report.issue_codes
        assert report.lifecycle_status == "STAGED_WITH_ISSUES"
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg42_missing_rights_metadata_blocks_staging(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher({"/jee-advanced-2026-syllabus.pdf": _slot_pdf(slot)})
    try:
        stage_official_slot(session, service, slot)
        source = _find_slot_source(session, slot.slot_id)
        assert source is not None
        source.copyright_classification = ""
        meta = dict(source.metadata_json or {})
        meta.pop("copyright_classification", None)
        meta.pop("rights_review_status", None)
        source.metadata_json = meta
        session.commit()
        report = stage_official_slot(session, service, slot)
        assert "RIGHTS_REVIEW_PENDING" in report.issue_codes
        assert report.lifecycle_status == "RIGHTS_REVIEW_PENDING"
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg42_inventory_not_staged_vs_fetch_blocked(tmp_path: Path) -> None:
    db_path = tmp_path / "inv.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / "inv-private")
    session = Session(engine)
    try:
        register_discovery_sources(session)
        session.commit()
        inventory = build_provenance_inventory_from_session(session, storage)
        slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "brochure" in s.slot_id)
        row = next(r for r in inventory["slots"] if r["slot_id"] == slot.slot_id)
        assert row["lifecycle_status"] == "NOT_STAGED_HERE"
        assert row["blocked_reason"] == "NOT_STAGED_HERE"
        assert row["observed_final_url"] is None
        assert row["fetch_response_content_type"] is None

        source = _find_slot_source(session, slot.slot_id)
        assert source is not None
        session.add(
            SourceAuditEvent(
                source_id=str(source.id),
                event_type="source_ingestion_failed",
                outcome="failure",
                payload_json={"reason": "synthetic_test_failure"},
            )
        )
        session.commit()
        inventory_blocked = build_provenance_inventory_from_session(session, storage)
        row_blocked = next(
            r for r in inventory_blocked["slots"] if r["slot_id"] == slot.slot_id
        )
        assert row_blocked["lifecycle_status"] == "FETCH_BLOCKED"
        assert row_blocked["blocked_reason"] == "FETCH_BLOCKED"
    finally:
        session.close()
        create_database_engine.cache_clear()


def _audit_event_types(session: Session) -> list[str]:
    return list(
        session.scalars(select(SourceAuditEvent.event_type)).all()
    )


@pytest.mark.parametrize(
    "protected_status",
    [
        SourceRevisionStatus.APPROVED,
        SourceRevisionStatus.SUPERSEDED,
    ],
)
def test_stg43_preflight_skips_ingest_when_protected_blob_missing(
    tmp_path: Path,
    protected_status: SourceRevisionStatus,
) -> None:
    """STG43-01: missing blob on trusted revision must not trigger Day3 restore/ingest."""

    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    db_path = tmp_path / f"preflight-{protected_status.value}.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / f"preflight-{protected_status.value}-private")
    session = Session(engine)
    service = SourceIntelligenceService(session, storage=storage)
    payload = _slot_pdf(slot)
    service.fetcher = _mock_fetcher({"/p1_english.pdf": payload})
    try:
        first = stage_official_slot(session, service, slot)
        session.commit()
        revision = session.get(SourceRevision, first.revision_id)
        assert revision is not None
        preserved_meta = {"trusted_snapshot": protected_status.value, "no_lock": True}
        revision.metadata_json = preserved_meta
        revision.status = protected_status.value
        revision.approved_by = "human-curator-test"
        revision.approval_fingerprint = f"fp-{protected_status.value}"
        storage_path = revision.storage_path
        assert storage_path is not None
        assert storage.exists(storage_path)
        storage.delete(storage_path)
        assert not storage.exists(storage_path)
        session.commit()
        rev_id = str(revision.id)
        audits_before = _audit_event_types(session)
    finally:
        session.close()
        create_database_engine.cache_clear()

    engine2 = create_database_engine(f"sqlite:///{db_path}")
    session2 = Session(engine2)
    service2 = SourceIntelligenceService(session2, storage=storage)
    service2.fetcher = _mock_fetcher({"/p1_english.pdf": payload})
    try:
        second = stage_official_slot(session2, service2, slot)
        session2.commit()
        assert second.lifecycle_status == "TRUSTED_REVISION_IMMUTABLE"
        assert "EXISTING_TRUSTED_REVISION_READ_ONLY" in second.issue_codes
        audits_after = _audit_event_types(session2)
        assert audits_after == audits_before
        forbidden = {
            "source_content_restored",
            "duplicate_content_detected",
            "source_ingested",
        }
        assert forbidden.isdisjoint(set(audits_after) - set(audits_before))
        revision2 = session2.get(SourceRevision, rev_id)
        assert revision2 is not None
        assert revision2.metadata_json == preserved_meta
        assert revision2.approval_fingerprint == f"fp-{protected_status.value}"
        assert not storage.exists(storage_path or "")
    finally:
        session2.close()
        create_database_engine.cache_clear()


def test_stg43_conflicting_years_2026_and_2027_in_content() -> None:
    payload = _simple_pdf_bytes(
        "JEE Advanced Paper 1 2026 p1_english future reference 2027"
    )
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.paper_1",
        final_url="https://jeeadv.ac.in/documents/p1_english.pdf",
        filename="p1_english.pdf",
        content=payload,
    )
    assert "CONFLICTING_DOCUMENT_YEARS" in issues


def test_stg43_paper1_with_answer_key_text_not_clean_staged(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    session, service = _session(tmp_path)
    mixed = _simple_pdf_bytes(
        "JEE Advanced Paper 1 2026 p1_english final answer key p1_solutions"
    )
    service.fetcher = _mock_fetcher({"/p1_english.pdf": mixed})
    try:
        report = stage_official_slot(session, service, slot)
        assert "content_question_paper_answer_key_mixup" in report.issue_codes
        assert report.lifecycle_status == "STAGED_WITH_ISSUES"
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_stg43_valid_2026_control_still_stages(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher({"/p1_english.pdf": _slot_pdf(slot)})
    try:
        report = stage_official_slot(session, service, slot)
        assert report.sha256
        assert "CONFLICTING_DOCUMENT_YEARS" not in report.issue_codes
        assert "content_question_paper_answer_key_mixup" not in report.issue_codes
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_redirect_final_url_recorded(tmp_path: Path) -> None:
    session, service = _session(tmp_path)
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "syllabus" in s.slot_id)

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("redirect.pdf"):
            return httpx.Response(
                302,
                request=request,
                headers={"location": "https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf"},
            )
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "application/pdf"},
            content=_slot_pdf(slot),
        )

    service.fetcher = SourceUrlFetcher(
        timeout_seconds=2,
        max_bytes=4096,
        max_redirects=2,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(redirect),
    )
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        assert report.final_url and "jee-advanced-2026-syllabus.pdf" in report.final_url
    finally:
        session.close()
        create_database_engine.cache_clear()

