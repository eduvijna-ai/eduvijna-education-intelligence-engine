from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.blueprint_snapshot import load_production_blueprint_snapshot
from app.jee_main_exam_intelligence.constants import (
    JEE_MAIN_EXAM_PACK_CODE,
    JEE_MAIN_VERSION_2027,
    NTA_2027_BULLETIN_SOURCE_CODE,
    NTA_2027_SYLLABUS_SOURCE_CODE,
)
from app.jee_main_exam_intelligence.enums import OfficialPatternAuthorityStatus
from app.jee_main_exam_intelligence.exam_catalogue import (
    ensure_jee_main_exam_catalogue,
    get_exam_version,
)
from app.jee_main_exam_intelligence.fixtures import (
    seed_day11_fixture_context,
    synthetic_activate_nta_sources_for_harness,
)
from app.jee_main_exam_intelligence.historical_evidence import build_historical_analytics_report
from app.jee_main_exam_intelligence.source_authority import (
    _revision_is_production_nta_approved,
    evaluate_official_pattern_authority,
    register_nta_2027_candidate_sources,
)
from app.models.enums import SourceExtractionStatus, SourceIngestionMethod
from app.models.examination import ExamBlueprintRule
from app.models.source import SourceAuditEvent, SourceRevision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_nta_candidates_stage_without_verification() -> None:
    with _session() as session:
        ids = register_nta_2027_candidate_sources(session)
        session.commit()
        assert NTA_2027_BULLETIN_SOURCE_CODE in ids
        assert NTA_2027_SYLLABUS_SOURCE_CODE in ids
        ensure_jee_main_exam_catalogue(session)
        version = get_exam_version(
            session, pack_code=JEE_MAIN_EXAM_PACK_CODE, version_code=JEE_MAIN_VERSION_2027
        )
        status, refs, _ = evaluate_official_pattern_authority(
            session,
            exam_version=version,
            exam_version_code=JEE_MAIN_VERSION_2027,
        )
        assert status == OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED
        assert all(not r.verified_for_official_pattern for r in refs)


def _mark_blueprint_synthetic_test_approved(session: Session):
    """Test-only rule setup; never constitutes NTA source approval."""
    ensure_jee_main_exam_catalogue(session)
    version = get_exam_version(
        session, pack_code=JEE_MAIN_EXAM_PACK_CODE, version_code=JEE_MAIN_VERSION_2027
    )
    assert version is not None
    version.metadata_json = {
        **(version.metadata_json or {}),
        "official_pattern_verified": True,
        "pinned_source_revision_ids": ["synthetic-bulletin-id", "synthetic-syllabus-id"],
    }
    rules = session.scalars(
        select(ExamBlueprintRule).where(ExamBlueprintRule.exam_version_id == version.id)
    ).all()
    for rule in rules:
        rule.metadata_json = {**(rule.metadata_json or {}), "verified_official": True}
    session.flush()
    return version, rules


def test_official_snapshot_requires_every_section_and_consistent_marks() -> None:
    with _session() as session:
        version, rules = _mark_blueprint_synthetic_test_approved(session)
        snapshot = load_production_blueprint_snapshot(session, version)
        assert snapshot is not None
        assert snapshot.total_questions == 75
        assert snapshot.section_a_mcq == 20
        assert snapshot.section_b_numerical == 5
        assert snapshot.total_marks == 300

        section_rule = next(r for r in rules if r.section_id is not None)
        old_marks = section_rule.marks_per_question
        section_rule.marks_per_question = 5
        session.flush()
        assert load_production_blueprint_snapshot(session, version) is None
        section_rule.marks_per_question = old_marks
        session.flush()

        session.delete(section_rule)
        session.flush()
        assert load_production_blueprint_snapshot(session, version) is None


def test_official_snapshot_rejects_mismatched_totals_and_unpinned_sources() -> None:
    with _session() as session:
        version, rules = _mark_blueprint_synthetic_test_approved(session)
        total_rule = next(r for r in rules if r.rule_type == "paper_total_questions")
        total_rule.exact_count = 74
        session.flush()
        assert load_production_blueprint_snapshot(session, version) is None
        total_rule.exact_count = 75
        version.metadata_json = {
            **version.metadata_json,
            "pinned_source_revision_ids": [],
        }
        session.flush()
        assert load_production_blueprint_snapshot(session, version) is None


def test_genuine_2026_national_testing_agency_links_are_discovery_only() -> None:
    report = build_historical_analytics_report()
    papers = report["official_2026_discovered_links"]
    assert report["official_2026_discovered_link_count"] == 9
    assert len({entry["source_url"] for entry in papers}) == 9
    assert all(entry["year"] == 2026 for entry in papers)
    assert all(entry["status"].endswith("not_curator_approved") for entry in papers)
    assert all(entry["source_url"].startswith("https://cdnbbsr.s3waas.gov.in/") for entry in papers)
    assert all(
        entry["rights_status"] == "official_public_link_only_no_question_redistribution"
        for entry in papers
    )
    assert report["historical_topic_frequencies_verified"] is False
    assert report["original_pdf_source_revisions_approved"] == 0
    assert report["mandatory_nta_quotas_invented"] is False


def test_pdf_metadata_and_fake_curator_fields_cannot_activate_json(tmp_path: Path) -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        synthetic_activate_nta_sources_for_harness(
            session, exam_version_id=ctx["exam_version_2027_id"], storage_root=tmp_path / "store"
        )
        session.flush()
        candidates = session.scalars(select(SourceRevision)).all()
        revision = next(
            r for r in candidates
            if (r.source.metadata_json or {}).get("eduvijna_source_code")
            == NTA_2027_BULLETIN_SOURCE_CODE
        )
        revision.metadata_json = {
            "page_locators": [{"page": 1, "section": "Paper 1"}],
        }
        revision.content_type = "application/pdf"
        revision.ingestion_method = SourceIngestionMethod.PDF.value
        revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
        revision.validated_checksum = revision.checksum
        revision.extracted_checksum = revision.checksum
        revision.approved_by = "self-attested-curator"
        revision.approved_at = datetime.now(UTC)
        revision.activated_at = datetime.now(UTC)
        revision.approval_fingerprint = "0" * 64
        session.add(
            SourceAuditEvent(
                source_id=revision.source_id,
                source_revision_id=revision.id,
                event_type="source_approved",
                outcome="success",
                actor_id="self-attested-curator",
                payload_json={},
            )
        )
        session.flush()
        assert not _revision_is_production_nta_approved(
            session, revision, NTA_2027_BULLETIN_SOURCE_CODE
        )
