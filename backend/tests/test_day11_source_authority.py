from __future__ import annotations

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
from app.jee_main_exam_intelligence.historical_evidence import build_historical_analytics_report
from app.jee_main_exam_intelligence.source_authority import (
    evaluate_official_pattern_authority,
    register_nta_2027_candidate_sources,
)
from app.models.examination import ExamBlueprintRule


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
    assert all(entry["rights_status"] == "official_public_link_only_no_question_redistribution" for entry in papers)
    assert report["historical_topic_frequencies_verified"] is False
    assert report["original_pdf_source_revisions_approved"] == 0
    assert report["mandatory_nta_quotas_invented"] is False
