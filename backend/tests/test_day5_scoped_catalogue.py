"""Synthetic catalogue contracts; these fixtures do not establish official coverage."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.curriculum_intelligence.scoped_catalogue import (
    STORAGE_KEY,
    CatalogueQuery,
    CatalogueSnapshot,
    CourseApplicability,
    ScopedCatalogueError,
    ScopedCatalogueRow,
    decode_utf8,
    materialize_catalogue,
    normalize_label,
    persisted_catalogue_coverage,
    query_catalogue,
    reconcile_coverage,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.db.base import Base
from app.models.curriculum import CurriculumPack, CurriculumVersion
from app.models.source import SourceRevision

CONTENT = "<html><h1>తెలుగు اردو</h1></html>".encode()
CHECKSUM = hashlib.sha256(CONTENT).hexdigest()


def row(**changes: Any) -> ScopedCatalogueRow:
    return ScopedCatalogueRow.model_validate(
        {
            "pack_id": "pack",
            "version_id": "version",
            "source_revision_id": "revision",
            "source_checksum": CHECKSUM,
            "source_locator": "table 1 row 1",
            "official_label": "తెలుగు",
            "grade": "VIII",
            "academic_year": "2025-26",
            "instructional_medium": "Telugu",
            "subject_language": "Telugu",
            "language_role": "first",
            "book_part": "1",
            "bilingual": "no",
            "course_family": "General",
            "resource_kind": "textbook",
            **changes,
        }
    )


def snapshot(*rows: ScopedCatalogueRow, **changes: Any) -> CatalogueSnapshot:
    return CatalogueSnapshot.model_validate(
        {
            "source_revision_id": "revision",
            "source_checksum": CHECKSUM,
            "rows": rows or (row(),),
            "extraction_method": "synthetic-table-v1",
            "inventory_status": "complete",
            **changes,
        }
    )


def test_unicode_roundtrip_preserves_official_text_and_separate_normalization() -> None:
    original = row(official_label=" తెలుగు اردو हिन्दी  ")
    restored = ScopedCatalogueRow.model_validate_json(original.model_dump_json())
    assert restored.official_label == " తెలుగు اردو हिन्दी  "
    assert restored.normalized_label == "తెలుగు اردو हिन्दी"
    assert decode_utf8(CONTENT) == CONTENT.decode()
    assert normalize_label("TELUGU") == normalize_label("Telugu")


@pytest.mark.parametrize("text", ["\ufffd", "à°¤", "Ã©", "\ud800", "x\x00y", ""])
def test_corrupt_unicode_is_rejected_instead_of_repaired(text: str) -> None:
    with pytest.raises((ValidationError, ScopedCatalogueError)):
        row(official_label=text)


def test_bad_utf8_source_rejected() -> None:
    with pytest.raises(ScopedCatalogueError, match="UTF-8"):
        decode_utf8(b"\xff")


@pytest.mark.parametrize(
    "field,value",
    [
        ("pack_id", "other"),
        ("version_id", "other"),
        ("grade", "IX"),
        ("academic_year", "2026-27"),
        ("instructional_medium", "English"),
        ("subject_language", "Urdu"),
        ("language_role", "second"),
        ("book_part", "2"),
        ("bilingual", "yes"),
        ("course_family", "Vocational"),
    ],
)
def test_every_scope_dimension_separates_identity(field: str, value: str) -> None:
    assert row().identity != row(**{field: value}).identity
    result = query_catalogue((row(), row(**{field: value})), CatalogueQuery())
    assert result.status == "ambiguous"
    result = query_catalogue((row(), row(**{field: value})), CatalogueQuery(**{field: value}))
    assert result.status == "matched"
    assert getattr(result.rows[0], field) == value


def test_case_alias_does_not_duplicate_or_overwrite_original() -> None:
    assert row(official_label="Telugu").identity == row(official_label="TELUGU").identity
    with pytest.raises(ValidationError, match="Duplicate normalized"):
        snapshot(row(official_label="Telugu"), row(official_label="TELUGU"))
    with pytest.raises(ValidationError, match="Alias collision"):
        snapshot(
            row(official_label="Telugu", aliases=("first language",)),
            row(official_label="Urdu", aliases=("FIRST LANGUAGE",)),
        )
    # The same alias in a different medium is valid and explicitly ambiguous.
    records = (
        row(official_label="Telugu", aliases=("language",)),
        row(official_label="Urdu", aliases=("language",), instructional_medium="Urdu"),
    )
    snapshot(*records)
    assert query_catalogue(records, CatalogueQuery(label="LANGUAGE")).status == "ambiguous"


def test_unknown_medium_and_applicability_never_become_defaults() -> None:
    assert (
        query_catalogue(
            (row(instructional_medium="unknown"),), CatalogueQuery(instructional_medium="English")
        ).status
        == "unknown_scope"
    )
    assert query_catalogue((row(),), CatalogueQuery(course_group="MPC")).status == "unknown_scope"
    assert not CourseApplicability().allows("MPC")
    assert query_catalogue((row(),), CatalogueQuery(label="not present")).status == "no_match"


def test_explicit_course_scope_requires_evidence_and_never_promotes_other_groups() -> None:
    with pytest.raises(ValidationError):
        CourseApplicability(status="explicit_all")
    with pytest.raises(ValidationError):
        CourseApplicability(status="unknown", groups=("MPC",))
    applicability = CourseApplicability(
        status="explicit_groups", groups=("MPC",), source_locator="table group column"
    )
    assert applicability.allows("mpc")
    assert not applicability.allows("BPC")
    result = query_catalogue(
        (row(applicability=applicability),), CatalogueQuery(course_group="BPC")
    )
    assert result.status == "no_match"


def test_snapshot_disallows_empty_inventory_and_mixed_revision() -> None:
    with pytest.raises(ValidationError):
        snapshot(rows=())
    with pytest.raises(ValidationError, match="Mixed source"):
        snapshot(row(source_revision_id="other"))


def test_coverage_reconciles_actual_unique_metadata_without_syllabus_claims() -> None:
    source = snapshot(row(), row(book_part="2"))
    complete = reconcile_coverage(source, source.rows)
    assert complete.status == "complete"
    assert complete.materialized_metadata_count == 2
    assert complete.governing_syllabus_membership_count == 0
    assert not complete.complete_curriculum
    assert reconcile_coverage(None, ()).status == "failed"
    assert reconcile_coverage(source, ()).status == "failed"
    duplicate = reconcile_coverage(source, (source.rows[0], source.rows[0]))
    assert duplicate.status == "failed" and duplicate.materialized_metadata_count == 1
    assert duplicate.missing_ids and duplicate.duplicate_ids
    assert reconcile_coverage(source, (row(book_part="3"),)).unexpected_ids
    assert reconcile_coverage(snapshot(inventory_status="partial"), (row(),)).status == "partial"
    changed = row(source_locator="tampered location")
    assert reconcile_coverage(snapshot(), (changed,)).conflicting_ids


def _materialization_context() -> tuple[
    CurriculumIntelligenceService, CurriculumVersion, SourceRevision
]:
    service = MagicMock(spec=CurriculumIntelligenceService)
    service.session = MagicMock()
    service.has_source_content.side_effect = CurriculumIntelligenceService.has_source_content
    service.source_service = SimpleNamespace(storage=SimpleNamespace(read=lambda path: CONTENT))
    revision = cast(
        SourceRevision,
        SimpleNamespace(
            id="revision",
            checksum=CHECKSUM,
            status="active",
            storage_path="fixture.html",
            ingestion_method="url",
            extraction_status="succeeded",
            extracted_checksum=CHECKSUM,
            extracted_text=CONTENT.decode(),
        ),
    )
    version = CurriculumVersion(
        id="version",
        curriculum_pack_id="pack",
        version_code="synthetic",
        metadata_json={"untouched": True},
    )
    return service, version, revision


def test_metadata_materialization_is_idempotent_and_retains_lossless_rows() -> None:
    service, version, revision = _materialization_context()
    materialize_catalogue(service, version, revision, snapshot())
    first = version.metadata_json.copy()
    materialize_catalogue(service, version, revision, snapshot())
    assert version.metadata_json == first
    stored = version.metadata_json[STORAGE_KEY][revision.id]["rows"]
    assert stored[0]["official_label"] == "తెలుగు"
    assert stored[0]["normalized_label"] == "తెలుగు"
    assert stored[0]["curriculum_membership_effect"] == "none"
    assert version.nodes == []
    assert version.metadata_json["untouched"]
    with pytest.raises(ScopedCatalogueError, match="immutable"):
        materialize_catalogue(service, version, revision, snapshot(row(official_label="Urdu")))


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("status", "staged"),
        ("ingestion_method", "manual"),
        ("extracted_checksum", "0" * 64),
        ("storage_path", None),
        ("checksum", "0" * 64),
    ],
)
def test_missing_stale_tampered_and_manual_bytes_fail_closed(attribute: str, value: Any) -> None:
    service, version, revision = _materialization_context()
    setattr(revision, attribute, value)
    with pytest.raises(ScopedCatalogueError):
        materialize_catalogue(service, version, revision, snapshot())
    assert STORAGE_KEY not in version.metadata_json


def test_wrong_revision_and_cross_pack_rejected_without_writes() -> None:
    service, version, revision = _materialization_context()
    wrong = snapshot(row(source_revision_id="other"), source_revision_id="other")
    with pytest.raises(ScopedCatalogueError, match="exact source revision"):
        materialize_catalogue(service, version, revision, wrong)
    with pytest.raises(ScopedCatalogueError, match="Cross-pack"):
        materialize_catalogue(service, version, revision, snapshot(row(pack_id="other")))
    assert STORAGE_KEY not in version.metadata_json


def test_unicode_metadata_survives_real_database_roundtrip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    service, version, revision = _materialization_context()
    with Session(engine) as session:
        pack = CurriculumPack(id="pack", code="synthetic", name="Synthetic", country="India")
        session.add_all([pack, version])
        session.flush()
        service.session = session
        original = row(official_label="తెలుగు اردو हिन्दी", aliases=("Telugu", "TELUGU"))
        materialize_catalogue(service, version, revision, snapshot(original))
        session.commit()
        session.expire_all()
        restored = session.get(CurriculumVersion, "version")
        assert restored is not None
        saved = restored.metadata_json[STORAGE_KEY][revision.id]
        restored_snapshot = CatalogueSnapshot.model_validate(saved["snapshot"])
        assert restored_snapshot.rows == (original,)
        assert saved["rows"][0]["official_label"] == original.official_label
    engine.dispose()


def test_query_does_not_silently_overwrite_conflicting_originals() -> None:
    with pytest.raises(ScopedCatalogueError, match="Conflicting rows"):
        query_catalogue(
            (row(official_label="Telugu"), row(official_label="TELUGU")), CatalogueQuery()
        )


def test_coverage_reads_actual_persisted_ids_and_detects_missing_or_tampered_rows() -> None:
    service, version, revision = _materialization_context()
    assert persisted_catalogue_coverage(version, revision.id).status == "failed"
    materialize_catalogue(service, version, revision, snapshot())
    assert persisted_catalogue_coverage(version, revision.id).status == "complete"
    saved = version.metadata_json[STORAGE_KEY][revision.id]
    saved["rows"][0]["id"] = "invented"
    with pytest.raises(ScopedCatalogueError, match="row identity"):
        persisted_catalogue_coverage(version, revision.id)
    saved["rows"] = []
    assert persisted_catalogue_coverage(version, revision.id).status == "failed"
    saved["snapshot_id"] = "invented"
    with pytest.raises(ScopedCatalogueError, match="snapshot identity"):
        persisted_catalogue_coverage(version, revision.id)


@pytest.mark.parametrize(
    "dimension", ["pack_id", "version_id", "grade", "academic_year", "instructional_medium"]
)
def test_unspecified_query_never_hides_unknown_essential_scope(dimension: str) -> None:
    result = query_catalogue((row(**{dimension: "unknown"}),), CatalogueQuery())
    assert result.status == "unknown_scope"
    assert dimension in result.unresolved_dimensions


def test_single_fully_scoped_inventory_hit_is_a_search_result_not_default_inference() -> None:
    result = query_catalogue((row(),), CatalogueQuery(label="తెలుగు"))
    assert result.status == "matched" and result.rows == (row(),)
    assert result.rows[0].curriculum_membership_effect == "none"


@pytest.mark.parametrize(
    "kind",
    ["learning_outcome", "academic_standard", "pedagogy", "calendar", "framework", "catalogue"],
)
def test_all_document_families_can_be_catalogued_without_membership(kind: str) -> None:
    item = row(resource_kind=kind)
    assert item.curriculum_membership_effect == "none"
