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
from app.jee_advanced.source_ingest_staging import (
    MANUAL_UPLOAD_INSTRUCTION,
    UntrustedOriginError,
    assert_no_curator_approval_events,
    assert_official_jeeadv_https_url,
    build_redacted_inventory,
    export_src01_manifest,
    slot_identity_issue_codes,
    stage_official_slot,
)
from app.jee_advanced.source_registry import (
    JEE_ADVANCED_2026_SOURCE_SLOTS,
    reference_evidence_ready,
)
from app.models import Source, SourceAuditEvent
from app.source_intelligence.security import SourceUrlFetcher, UnsafeSourceUrl, validate_source_url
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
    service.fetcher = _mock_fetcher({"/jee-advanced-2026-syllabus.pdf": _minimal_pdf("syllabus")})
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
    handlers = {"/jee-advanced-2026-syllabus.pdf": _minimal_pdf("syllabus")}
    session, service = _session(tmp_path)
    service.fetcher = _mock_fetcher(handlers)
    try:
        report = stage_official_slot(session, service, slot)
        session.commit()
        assert report.sha256
        assert report.lifecycle_status in {"STAGED", "STAGED_WITH_ISSUES"}
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
        url.rsplit("/", 1)[-1]: _minimal_pdf(name)
        for name, url in _ISSUE_URLS.items()
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
            content=_minimal_pdf("syllabus"),
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

