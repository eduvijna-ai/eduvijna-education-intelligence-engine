"""Issue #44 one-shot adversarial vectors for newly closed engineering gaps."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.constants import (
    BROCHURE_DISCOVERY_URL_ALTERNATE,
    BROCHURE_DISCOVERY_URL_PRIMARY,
)
from app.jee_advanced.constraint_precedence import (
    ConstraintLayer,
    resolve_constraint_layer,
)
from app.jee_advanced.core_test_fixtures import _simple_pdf_bytes
from app.jee_advanced.enums import JeeAdvancedSourceTrustMode
from app.jee_advanced.historical_inventory import build_historical_inventory
from app.jee_advanced.source_ingest_staging import (
    _slot_discovery_urls,
    slot_identity_issue_codes,
    stage_official_slot,
)
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS
from app.jee_advanced.syllabus_catalogue import CatalogueStatus, build_reference_syllabus_catalogue
from app.jee_advanced.verification_orchestration import (
    VerificationOutcome,
    bounded_repair_allowed,
    verify_mcq_answer,
    verify_numerical_answer,
    verify_stem_assets,
)
from app.models import SourceAuditEvent, SourceRevision
from app.models.enums import SourceRevisionStatus
from app.source_intelligence.security import SourceUrlFetcher
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

_PUBLIC_RESOLVER = lambda _h: ["93.184.216.34"]  # noqa: E731


def _session(tmp_path: Path) -> tuple[Session, SourceIntelligenceService]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'oneshot.sqlite'}")
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
        return httpx.Response(404, request=request)

    return SourceUrlFetcher(
        timeout_seconds=3,
        max_bytes=8_000_000,
        max_redirects=3,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(route),
    )


def _slot_pdf(slot_id: str) -> bytes:
    if "brochure" in slot_id:
        return _simple_pdf_bytes("JEE Advanced information brochure 2026 IBEnglish")
    return _simple_pdf_bytes(f"JEE Advanced Paper 1 2026 p1_english slot {slot_id}")


def test_brochure_discovery_includes_alternate_url() -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "brochure" in s.slot_id)
    urls = _slot_discovery_urls(slot)
    assert BROCHURE_DISCOVERY_URL_PRIMARY in urls
    assert BROCHURE_DISCOVERY_URL_ALTERNATE in urls


def test_brochure_falls_back_to_alternate_on_primary_404(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "brochure" in s.slot_id)
    session, service = _session(tmp_path)
    payload = _slot_pdf(slot.slot_id)
    service.fetcher = _mock_fetcher(
        {
            "IBEnglish_2026_1.pdf": payload,
        }
    )
    try:
        report = stage_official_slot(session, service, slot)
        assert report.sha256
        assert report.final_url and "IBEnglish_2026_1.pdf" in report.final_url
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_conflicting_years_2024_and_2026_in_content() -> None:
    payload = _simple_pdf_bytes("JEE Advanced 2024 archive notice with 2026 syllabus cross-ref")
    issues = slot_identity_issue_codes(
        "jee_advanced.2026.syllabus",
        final_url="https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf",
        filename="jee-advanced-2026-syllabus.pdf",
        content=payload,
    )
    assert "CONFLICTING_DOCUMENT_YEARS" in issues


def test_protected_revision_missing_storage_path_preflight(tmp_path: Path) -> None:
    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id.endswith("paper_1"))
    db_path = tmp_path / "missing-path.sqlite"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(tmp_path / "missing-path-private")
    session = Session(engine)
    service = SourceIntelligenceService(session, storage=storage)
    payload = _simple_pdf_bytes("JEE Advanced Paper 1 2026 p1_english")
    service.fetcher = _mock_fetcher({"/p1_english.pdf": payload})
    try:
        first = stage_official_slot(session, service, slot)
        session.commit()
        revision = session.get(SourceRevision, first.revision_id)
        assert revision is not None
        revision.status = SourceRevisionStatus.APPROVED.value
        revision.storage_path = None
        session.commit()
        audits_before = list(session.scalars(select(SourceAuditEvent.event_type)).all())
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
        audits_after = list(session2.scalars(select(SourceAuditEvent.event_type)).all())
        assert audits_after == audits_before
    finally:
        session2.close()
        create_database_engine.cache_clear()


def test_syllabus_catalogue_source_pending_without_active_revision(tmp_path: Path) -> None:
    session, _service = _session(tmp_path)
    try:
        report = build_reference_syllabus_catalogue(session)
        assert report.status == CatalogueStatus.SOURCE_PENDING
        assert "syllabus_active_revision_missing" in report.issue_codes
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_historical_inventory_marks_missing_bytes() -> None:
    session = Session(create_database_engine("sqlite:///:memory:"))
    Base.metadata.create_all(session.bind)
    try:
        report = build_historical_inventory(session)
        assert report.issue_codes
        assert all("original_bytes_not_in_repo" in code for code in report.issue_codes)
    finally:
        session.close()


def test_constraint_precedence_official_over_soft() -> None:
    layer = resolve_constraint_layer(
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        official_rule_pin_present=True,
    )
    assert layer == ConstraintLayer.OFFICIAL_APPROVED


def test_verification_orchestration_review_paths() -> None:
    mcq = verify_mcq_answer(selected="A", correct="A", independent_solver_evidence=None)
    assert mcq.outcome == VerificationOutcome.REVIEW_REQUIRED
    num = verify_numerical_answer(
        submitted="1.0",
        expected="1.0",
        tolerance=None,
        units_required=False,
        independent_solver_evidence={"kind": "independent_solver"},
    )
    assert num.outcome == VerificationOutcome.REVIEW_REQUIRED
    stem = verify_stem_assets(latex="x^2", has_image=True, alt_text=None)
    assert stem.outcome == VerificationOutcome.REVIEW_REQUIRED
    repair = bounded_repair_allowed(repairs_used=3)
    assert repair.outcome == VerificationOutcome.FAIL