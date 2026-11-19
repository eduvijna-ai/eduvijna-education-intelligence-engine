"""D12-RELIABILITY-01: read-only authority and bootstrap regression tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.constants import VERSION_REFERENCE_2026
from app.jee_advanced.core_test_fixtures import seed_all_core_source_slots
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.source_authority import (
    ReferenceAuthorityReport,
    SlotAuthorityResult,
    evaluate_reference_authority,
)
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models.examination import ExamPack, ExamVersion


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'rel.db'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _count_rows(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _artificial_all_slots_trusted(
    _session: Session, slot_id: str, **_kw: object
) -> SlotAuthorityResult:
    return SlotAuthorityResult(
        slot_id=slot_id,
        trusted=True,
        revision_id="artificial-revision",
        source_id="artificial-source",
        issues=(),
    )


def test_rel_authority_readonly_no_pack_no_inserts(db_session: Session) -> None:
    assert _count_rows(db_session, ExamPack) == 0
    assert _count_rows(db_session, ExamVersion) == 0

    with patch(
        "app.jee_advanced.source_authority.evaluate_slot_authority",
        side_effect=_artificial_all_slots_trusted,
    ):
        report = evaluate_reference_authority(db_session)

    assert isinstance(report, ReferenceAuthorityReport)
    assert report.ready is False
    assert "reference_exam_version_missing" in report.issues
    assert _count_rows(db_session, ExamPack) == 0
    assert _count_rows(db_session, ExamVersion) == 0


def test_rel_authority_no_recursion_with_artificial_slots(db_session: Session) -> None:
    with patch(
        "app.jee_advanced.source_authority.evaluate_slot_authority",
        side_effect=_artificial_all_slots_trusted,
    ):
        evaluate_reference_authority(db_session)
        evaluate_reference_authority(db_session)


def test_rel_pack_without_reference_version_non_pass(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    db_session.commit()
    version_count = _count_rows(db_session, ExamVersion)

    with patch(
        "app.jee_advanced.source_authority.evaluate_slot_authority",
        side_effect=_artificial_all_slots_trusted,
    ):
        report = evaluate_reference_authority(db_session)

    assert report.ready is False
    assert "reference_exam_version_missing" in report.issues
    assert _count_rows(db_session, ExamVersion) == version_count


def test_rel_reference_version_incomplete_blueprint(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    db_session.commit()
    pack_count = _count_rows(db_session, ExamPack)
    version_count = _count_rows(db_session, ExamVersion)

    with patch(
        "app.jee_advanced.source_authority.evaluate_slot_authority",
        side_effect=_artificial_all_slots_trusted,
    ):
        report = evaluate_reference_authority(db_session)

    assert report.ready is False
    assert any("reference_blueprint:" in issue for issue in report.issues)
    assert _count_rows(db_session, ExamPack) == pack_count
    assert _count_rows(db_session, ExamVersion) == version_count


def test_rel_repeated_calls_stable_row_counts(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'rel2.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_all_core_source_slots(session)
        session.commit()

    with Session(engine) as session:
        pack_count = _count_rows(session, ExamPack)
        version_count = _count_rows(session, ExamVersion)

    for _ in range(3):
        with Session(engine) as session:
            assert not reference_evidence_ready(session)
            assert not evaluate_reference_authority(session).ready
            assert _count_rows(session, ExamPack) == pack_count
            assert _count_rows(session, ExamVersion) == version_count


def test_rel_exam_version_metadata_no_stale_reference_flag(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    db_session.flush()
    meta = dict(version.metadata_json or {})
    assert meta.get("reference_sources_approved") is not True
    assert meta.get("reference_sources_approved_at_issuance") is False


def test_rel_synthetic_pdf_fixtures_never_official_ready(db_session: Session) -> None:
    seed_all_core_source_slots(db_session)
    assert reference_evidence_ready(db_session) is False


def test_rel_lookup_reference_version_readonly_helper(db_session: Session) -> None:
    from app.jee_advanced.exam_profile import lookup_reference_exam_version

    assert lookup_reference_exam_version(db_session) is None
    pack = ensure_jee_advanced_exam_pack(db_session)
    ref = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    db_session.commit()
    found = lookup_reference_exam_version(db_session)
    assert found is not None
    assert found.version_code == VERSION_REFERENCE_2026
    assert str(found.id) == str(ref.id)