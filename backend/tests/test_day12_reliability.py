"""D12-RELIABILITY / REL-F02-PROOF: read-only authority and bootstrap regression tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.authority import resolve_profile_authority
from app.jee_advanced.constants import VERSION_REFERENCE_2026
from app.jee_advanced.core_test_fixtures import seed_all_core_source_slots
from app.jee_advanced.enums import AdvancedPlanVerdict, AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.source_authority import SlotAuthorityResult, evaluate_reference_authority
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models import Source, SourceAuditEvent, SourceRevision
from app.models.enums import BlueprintRuleType
from app.models.examination import ExamBlueprintRule, ExamPack, ExamVersion


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


def _json_norm(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _identity_persistence_snapshot(session: Session) -> dict[str, object]:
    """Identity-bound read-only snapshot of all six authority-related models."""

    sources = session.scalars(select(Source).order_by(Source.id)).all()
    revisions = session.scalars(select(SourceRevision).order_by(SourceRevision.id)).all()
    audits = session.scalars(select(SourceAuditEvent).order_by(SourceAuditEvent.id)).all()
    packs = session.scalars(select(ExamPack).order_by(ExamPack.id)).all()
    versions = session.scalars(select(ExamVersion).order_by(ExamVersion.id)).all()
    rules = session.scalars(select(ExamBlueprintRule).order_by(ExamBlueprintRule.id)).all()

    return {
        "counts": {
            "source": len(sources),
            "source_revision": len(revisions),
            "source_audit_event": len(audits),
            "exam_pack": len(packs),
            "exam_version": len(versions),
            "exam_blueprint_rule": len(rules),
        },
        "sources": tuple(
            sorted((str(s.id), str(s.status)) for s in sources),
        ),
        "revisions": tuple(
            sorted(
                (
                    str(r.id),
                    str(r.source_id),
                    str(r.status),
                    str(r.checksum or ""),
                    str(r.validated_checksum or ""),
                    str(r.extracted_checksum or ""),
                    str(r.approved_by or ""),
                    str(r.approval_fingerprint or ""),
                )
                for r in revisions
            )
        ),
        "audits": tuple(
            sorted(
                (
                    str(a.id),
                    str(a.source_revision_id or ""),
                    str(a.event_type),
                    str(a.outcome),
                    str(a.actor_id or ""),
                )
                for a in audits
            )
        ),
        "exam_packs": tuple(
            sorted(
                (str(p.id), str(p.code), str(bool(p.active))) for p in packs
            )
        ),
        "exam_versions": tuple(
            sorted(
                (
                    str(v.id),
                    str(v.version_code),
                    str(v.status),
                    str(v.exam_pack_id),
                )
                for v in versions
            )
        ),
        "blueprint_rules": tuple(
            sorted(
                (
                    str(rule.id),
                    str(rule.exam_version_id),
                    str(rule.rule_type),
                    str(rule.section_id or ""),
                    _json_norm(rule.selector_json),
                    str(rule.exact_count),
                    str(rule.min_count),
                    str(rule.max_count),
                    str(rule.marks_per_question),
                    str(rule.negative_marks),
                )
                for rule in rules
            )
        ),
    }


def _authority_readout(session: Session) -> dict[str, object]:
    report = evaluate_reference_authority(session)
    ready = reference_evidence_ready(session)
    return {
        "reference_evidence_ready": ready,
        "report_ready": report.ready,
        "issues": tuple(report.issues),
        "slots": tuple(
            (slot.slot_id, slot.trusted, tuple(slot.issues)) for slot in report.slots
        ),
    }


@contextmanager
def _artificial_slot_patch() -> Iterator[None]:
    """TEST DOUBLE: all six slots appear trusted; not official IIT/JAB evidence."""

    def _trusted(_session: Session, slot_id: str, **_kw: object) -> SlotAuthorityResult:
        return SlotAuthorityResult(
            slot_id=slot_id,
            trusted=True,
            revision_id="artificial-revision",
            source_id="artificial-source",
            issues=(),
        )

    with patch(
        "app.jee_advanced.source_authority.evaluate_slot_authority",
        side_effect=_trusted,
    ):
        yield


def _assert_readouts_identical(
    readouts: list[dict[str, object]], *, expect_reference_version_missing: bool
) -> None:
    assert len(readouts) >= 3
    first = readouts[0]
    for item in readouts[1:]:
        assert item == first
    assert first["reference_evidence_ready"] is False
    assert first["report_ready"] is False
    if expect_reference_version_missing:
        assert "reference_exam_version_missing" in first["issues"]
        for _, trusted, issues in first["slots"]:
            assert trusted is True
            assert issues == ()


def test_rel_authority_readonly_no_pack_no_inserts(db_session: Session) -> None:
    assert _count_rows(db_session, ExamPack) == 0
    assert _count_rows(db_session, ExamVersion) == 0

    with _artificial_slot_patch():
        readout = _authority_readout(db_session)

    assert readout["reference_evidence_ready"] is False
    assert "reference_exam_version_missing" in readout["issues"]
    assert _count_rows(db_session, ExamPack) == 0
    assert _count_rows(db_session, ExamVersion) == 0


def test_rel_authority_no_recursion_with_artificial_slots(db_session: Session) -> None:
    with _artificial_slot_patch():
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

    with _artificial_slot_patch():
        readout = _authority_readout(db_session)

    assert readout["reference_evidence_ready"] is False
    assert "reference_exam_version_missing" in readout["issues"]
    assert _count_rows(db_session, ExamVersion) == version_count


def test_rel_reference_version_incomplete_blueprint(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    ref = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    db_session.commit()
    pack_count = _count_rows(db_session, ExamPack)
    version_count = _count_rows(db_session, ExamVersion)

    with _artificial_slot_patch():
        readout = _authority_readout(db_session)

    assert readout["reference_evidence_ready"] is False
    assert any("reference_blueprint:" in issue for issue in readout["issues"])
    assert _count_rows(db_session, ExamPack) == pack_count
    assert _count_rows(db_session, ExamVersion) == version_count
    snap = _identity_persistence_snapshot(db_session)
    version_ids = {row[0] for row in snap["exam_versions"]}  # type: ignore[index]
    assert str(ref.id) in version_ids


def test_rel_repeated_calls_stable_row_counts(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'rel2.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_all_core_source_slots(session)
        pack = ensure_jee_advanced_exam_pack(session)
        ref = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.REFERENCE_2026,
            academic_year="2026",
        )
        session.add(
            ExamBlueprintRule(
                exam_version_id=str(ref.id),
                rule_type=BlueprintRuleType.QUESTION_COUNT.value,
                exact_count=1,
                selector_json={"labeled_test_fixture": True},
                metadata_json={"incomplete_rel_fixture": True},
            )
        )
        session.commit()

    with Session(engine) as session:
        baseline = _identity_persistence_snapshot(session)

    readouts: list[dict[str, object]] = []
    for _ in range(3):
        with Session(engine) as session:
            readouts.append(_authority_readout(session))
            assert _identity_persistence_snapshot(session) == baseline

    _assert_readouts_identical(readouts, expect_reference_version_missing=False)
    assert readouts[0]["issues"]


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


def test_rel_evidence_f01_forged_version_metadata_does_not_bypass_authority(
    tmp_path: Path,
) -> None:
    """REL36-F01: metadata-only reference_sources_approved cannot override live checks."""

    engine = create_database_engine(f"sqlite:///{tmp_path / 'f01.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        pack = ensure_jee_advanced_exam_pack(session)
        version = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.REFERENCE_2026,
            academic_year="2026",
        )
        version.metadata_json = {
            **dict(version.metadata_json or {}),
            "reference_sources_approved": True,
            "reference_sources_approved_at_issuance": True,
        }
        session.commit()

    with Session(engine) as session:
        readout = _authority_readout(session)
        assert readout["reference_evidence_ready"] is False
        assert readout["issues"]

        ref_decision = resolve_profile_authority(
            profile_kind=AdvancedProfileKind.REFERENCE_2026,
            academic_year="2026",
            session=session,
        )
        assert ref_decision.verdict == AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED

        y2027 = resolve_profile_authority(
            profile_kind=AdvancedProfileKind.CANDIDATE_2027,
            academic_year="2027",
            session=session,
        )
        assert y2027.verdict == AdvancedPlanVerdict.OFFICIAL_PATTERN_NOT_VERIFIED


def test_rel_evidence_f02_artificial_slots_never_mutate_authority_tables(
    tmp_path: Path,
) -> None:
    """
    REL37-F02a: artificial test-double trusted slots; full issue readout stable.
    Not official IIT/JAB proof.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'f02.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        baseline = _identity_persistence_snapshot(session)

    readouts: list[dict[str, object]] = []
    for _ in range(3):
        with Session(engine) as session:
            with _artificial_slot_patch():
                readouts.append(_authority_readout(session))
            assert _identity_persistence_snapshot(session) == baseline

    _assert_readouts_identical(readouts, expect_reference_version_missing=True)
    for _, trusted, issues in readouts[0]["slots"]:  # type: ignore[index]
        assert trusted is True
        assert issues == ()


def test_rel_f02a_identity_snapshot_sensitive_to_fixture_rows(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'snap.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        empty = _identity_persistence_snapshot(session)
        assert empty["counts"]["source"] == 0  # type: ignore[index]

    with Session(engine) as session:
        seed_all_core_source_slots(session)
        pack = ensure_jee_advanced_exam_pack(session)
        ref = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.REFERENCE_2026,
            academic_year="2026",
        )
        session.commit()
        seeded = _identity_persistence_snapshot(session)
        assert seeded["counts"]["source"] == 6  # type: ignore[index]
        assert seeded["counts"]["source_revision"] == 6  # type: ignore[index]
        assert seeded["counts"]["exam_pack"] == 1  # type: ignore[index]
        assert seeded != empty
        assert reference_evidence_ready(session) is False

        session.add(
            ExamBlueprintRule(
                exam_version_id=str(ref.id),
                rule_type=BlueprintRuleType.QUESTION_COUNT.value,
                min_count=1,
                selector_json={"rel_f02a_labeled_fixture": True},
            )
        )
        session.commit()
        with_rule = _identity_persistence_snapshot(session)
        assert with_rule["counts"]["exam_blueprint_rule"] == 1  # type: ignore[index]
        assert with_rule != seeded
        assert reference_evidence_ready(session) is False