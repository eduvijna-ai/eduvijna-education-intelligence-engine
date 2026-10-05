"""Synthetic catalogue contracts; these fixtures do not establish official coverage."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.curriculum_intelligence.scoped_catalogue import (
    CATALOGUE_QUERY_DIMENSIONS,
    CATALOGUE_SOURCE_DIMENSIONS,
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
    validate_catalogue_row_scope,
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
            "subject": "Telugu",
            "subject_language": "Telugu",
            "applicability": CourseApplicability(
                status="explicit_groups", groups=("MPC",), source_locator="table group"
            ),
            "language_role": "first",
            "book_part": "1",
            "bilingual": "no",
            "course_family": "General",
            "resource_kind": "textbook",
            **changes,
        }
    )


def full_query(**changes: Any) -> CatalogueQuery:
    source = row()
    return CatalogueQuery.model_validate(
        {
            **{
                field: getattr(source, field)
                for field in CATALOGUE_QUERY_DIMENSIONS
                if field != "course_group"
            },
            "course_group": "MPC",
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
    assert result.status == "unknown_scope"
    result = query_catalogue((row(), row(**{field: value})), full_query(**{field: value}))
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
    assert query_catalogue(records, CatalogueQuery(label="LANGUAGE")).status == "unknown_scope"


def test_unknown_medium_and_applicability_never_become_defaults() -> None:
    assert (
        query_catalogue(
            (row(instructional_medium="unknown"),), CatalogueQuery(instructional_medium="English")
        ).status
        == "unknown_scope"
    )
    assert (
        query_catalogue((row(applicability=CourseApplicability()),), full_query()).status
        == "unknown_scope"
    )
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
    assert result.status == "unknown_scope"
    result = query_catalogue((row(),), full_query(label="తెలుగు"))
    assert result.status == "matched" and result.rows == (row(),)
    assert result.rows[0].curriculum_membership_effect == "none"


@pytest.mark.parametrize(
    "kind",
    ["learning_outcome", "academic_standard", "pedagogy", "calendar", "framework", "catalogue"],
)
def test_all_document_families_can_be_catalogued_without_membership(kind: str) -> None:
    item = row(resource_kind=kind)
    assert item.curriculum_membership_effect == "none"


@pytest.mark.parametrize("dimension", CATALOGUE_QUERY_DIMENSIONS)
@pytest.mark.parametrize("value", [None, "unknown", "", "   "])
def test_singleton_query_requires_each_explicit_dimension(
    dimension: str, value: str | None
) -> None:
    result = query_catalogue((row(),), full_query(**{dimension: value}))
    assert result.status == "unknown_scope"
    assert dimension in result.unresolved_dimensions


@pytest.mark.parametrize(
    "dimension", [d for d in CATALOGUE_QUERY_DIMENSIONS if d != "course_group"]
)
def test_singleton_query_requires_known_observed_dimension(dimension: str) -> None:
    result = query_catalogue((row(**{dimension: "unknown"}),), full_query())
    assert result.status == "unknown_scope"
    assert dimension in result.unresolved_dimensions


def approved_scope() -> Any:
    from app.curriculum_intelligence.scoped_curriculum import SourceCurriculumScope

    return SourceCurriculumScope(
        pack_code="pack",
        version_codes=("version",),
        grades=("VIII",),
        media=("Telugu",),
        subjects=("Telugu",),
        course_families=("General",),
        course_groups=("MPC",),
        subject_languages=("Telugu",),
        language_roles=("first",),
        book_parts=("1",),
        bilingual_states=("no",),
    )


def scope_version() -> Any:
    return SimpleNamespace(
        id="version",
        curriculum_pack_id="pack",
        version_code="version",
        academic_year="2025-26",
        curriculum_pack=SimpleNamespace(code="pack"),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("pack_id", "wrong"),
        ("version_id", "wrong"),
        ("academic_year", "2026-27"),
        ("grade", "IX"),
        ("instructional_medium", "English"),
        ("subject", "Mathematics"),
        ("course_family", "Vocational"),
        ("subject_language", "English"),
        ("language_role", "second"),
        ("book_part", "2"),
        ("bilingual", "yes"),
    ],
)
def test_each_catalogue_assertion_must_match_approved_inventory_scope(
    field: str, value: str
) -> None:
    with pytest.raises(ScopedCatalogueError, match="scope"):
        validate_catalogue_row_scope(scope_version(), row(**{field: value}), approved_scope())


@pytest.mark.parametrize(
    "field",
    [
        "pack_id",
        "version_id",
        "academic_year",
        "grade",
        "instructional_medium",
        "subject",
        "course_family",
        "subject_language",
        "language_role",
        "book_part",
        "bilingual",
    ],
)
def test_unknown_catalogue_scope_cannot_materialize(field: str) -> None:
    with pytest.raises(ScopedCatalogueError, match="scope"):
        validate_catalogue_row_scope(scope_version(), row(**{field: "unknown"}), approved_scope())


@pytest.mark.parametrize(
    "applicability",
    [
        CourseApplicability(),
        CourseApplicability(status="explicit_all", source_locator="table group"),
        CourseApplicability(
            status="explicit_groups", groups=("BPC",), source_locator="table group"
        ),
        CourseApplicability(
            status="explicit_groups", groups=("MPC", "BPC"), source_locator="table group"
        ),
    ],
)
def test_group_scope_cannot_be_widened(applicability: CourseApplicability) -> None:
    with pytest.raises(ScopedCatalogueError, match="course_group"):
        validate_catalogue_row_scope(
            scope_version(), row(applicability=applicability), approved_scope()
        )


def test_fully_approved_inventory_row_and_exact_query_work() -> None:
    validate_catalogue_row_scope(scope_version(), row(), approved_scope())
    assert query_catalogue((row(),), full_query()).status == "matched"


@pytest.mark.parametrize(
    "field",
    [
        "grades",
        "media",
        "subjects",
        "course_families",
        "course_groups",
        "subject_languages",
        "language_roles",
        "book_parts",
        "bilingual_states",
    ],
)
def test_omitted_approved_dimension_cannot_authorize_catalogue_claim(field: str) -> None:
    scope = approved_scope().model_copy(update={field: ()})
    with pytest.raises(ScopedCatalogueError, match="scope"):
        validate_catalogue_row_scope(scope_version(), row(), scope)


@pytest.mark.parametrize("dimension", CATALOGUE_QUERY_DIMENSIONS)
def test_each_conflicting_query_dimension_prevents_match(dimension: str) -> None:
    assert query_catalogue((row(),), full_query(**{dimension: "different"})).status == "no_match"


def bounded_inventory_context(
    source_changes: dict[str, Any] | None = None,
) -> tuple[Any, Any, Any, CatalogueSnapshot]:
    original = row().model_dump(include=set(CATALOGUE_SOURCE_DIMENSIONS) | {"resource_url"})
    original.update({"pack_code": "pack", "version_code": "version"})
    original["applicability"] = {"status": "explicit_groups", "groups": ["MPC"]}
    original.update(source_changes or {})
    other = original | {
        "grade": "IX",
        "instructional_medium": "English",
        "subject": "Mathematics",
        "course_family": "Vocational",
        "subject_language": "English",
        "language_role": "second",
        "book_part": "2",
        "bilingual": "yes",
        "official_label": "Other book",
        "academic_year": "2026-27",
        "resource_kind": "assessment",
        "resource_url": "https://example.invalid/other.pdf",
        "applicability": {"status": "explicit_groups", "groups": ["BPC"]},
    }
    content = json.dumps({"inventory": [original, other]}, ensure_ascii=False).encode()
    checksum = hashlib.sha256(content).hexdigest()
    service = MagicMock()
    service.has_source_content.return_value = True
    service.source_service.storage.read.return_value = content
    service.source_service._content_integrity.return_value = (content, None, True)
    service.source_service._snapshot_checksum.return_value = "metadata-checksum"
    service.source_service._approval_fingerprint.return_value = "approved"
    service._source_metadata.return_value = {
        "inventory_scope": approved_scope()
        .model_copy(update={"applicability_locator": "JSON pointer /inventory/0/applicability"})
        .model_dump()
    }
    revision = SimpleNamespace(
        id="revision",
        checksum=checksum,
        byte_size=len(content),
        status="active",
        storage_path="source.json",
        content_type="application/json",
        ingestion_method="json",
        extraction_status="succeeded",
        extracted_checksum=checksum,
        extracted_text=content.decode(),
        source_snapshot_checksum="metadata-checksum",
        approval_fingerprint="approved",
        metadata_json={
            "source_snapshot": {
                "metadata_json": {"verified_locators": ["fabricated", "JSON pointer /missing"]}
            }
        },
    )
    version = scope_version()
    version.status = "draft"
    version.metadata_json = {"scope_enforced": True}
    item = row(
        source_checksum=checksum,
        source_locator="JSON pointer /inventory/0",
        applicability=CourseApplicability(
            status="explicit_groups",
            groups=("MPC",),
            source_locator="JSON pointer /inventory/0/applicability",
        ),
    )
    return service, version, revision, snapshot(item, source_checksum=checksum)


def test_structured_original_inventory_row_binds_all_claimed_dimensions() -> None:
    service, version, revision, inventory = bounded_inventory_context()
    assert json.loads(revision.extracted_text)["inventory"][0]["applicability"]["groups"] == ["MPC"]
    assert materialize_catalogue(service, version, revision, inventory).status == "complete"


@pytest.mark.parametrize("field", ["source_locator", "applicability"])
@pytest.mark.parametrize(
    "locator", ["fabricated", "JSON pointer /missing", "JSON pointer /inventory/99/title"]
)
def test_both_inventory_locators_require_actual_original_structure(
    field: str, locator: str
) -> None:
    service, version, revision, inventory = bounded_inventory_context()
    item = inventory.rows[0]
    changes = {
        field: locator
        if field == "source_locator"
        else CourseApplicability(status="explicit_groups", groups=("MPC",), source_locator=locator)
    }
    changed = snapshot(item.model_copy(update=changes), source_checksum=revision.checksum)
    with pytest.raises(ValueError):
        materialize_catalogue(service, version, revision, changed)
    assert version.metadata_json == {"scope_enforced": True}
    service.session.flush.assert_not_called()


@pytest.mark.parametrize(
    "locator",
    [None, "fabricated", "JSON pointer /missing", "JSON pointer /inventory/99/group_note"],
)
def test_scope_applicability_locator_requires_original_structure(locator: str | None) -> None:
    service, version, revision, inventory = bounded_inventory_context()
    service._source_metadata.return_value["inventory_scope"]["applicability_locator"] = locator
    with pytest.raises(ValueError):
        materialize_catalogue(service, version, revision, inventory)
    assert version.metadata_json == {"scope_enforced": True}
    service.session.flush.assert_not_called()


@pytest.mark.parametrize(
    "field,allowed,value",
    [
        ("grade", "grades", "IX"),
        ("instructional_medium", "media", "English"),
        ("subject", "subjects", "Mathematics"),
        ("course_family", "course_families", "Vocational"),
        ("subject_language", "subject_languages", "English"),
        ("language_role", "language_roles", "second"),
        ("book_part", "book_parts", "2"),
        ("bilingual", "bilingual_states", "yes"),
        ("official_label", None, "Other book"),
        ("resource_kind", None, "assessment"),
        ("resource_url", None, "https://example.invalid/other.pdf"),
        ("academic_year", None, "2026-27"),
    ],
)
def test_globally_allowed_other_row_value_cannot_rebind_first_row(
    field: str, allowed: str | None, value: str
) -> None:
    service, version, revision, inventory = bounded_inventory_context()
    if allowed:
        service._source_metadata.return_value["inventory_scope"][allowed] += (value,)
    if field == "academic_year":
        version.academic_year = value
    changed = snapshot(
        inventory.rows[0].model_copy(update={field: value}), source_checksum=revision.checksum
    )
    with pytest.raises(ScopedCatalogueError, match="source row contradicts"):
        materialize_catalogue(service, version, revision, changed)
    assert version.metadata_json == {"scope_enforced": True}
    service.session.flush.assert_not_called()


@pytest.mark.parametrize(
    "locator",
    ["JSON pointer /inventory/0/applicability", "JSON pointer /inventory/1/applicability"],
)
def test_other_row_group_cannot_be_rebound_even_if_globally_approved(locator: str) -> None:
    service, version, revision, inventory = bounded_inventory_context()
    service._source_metadata.return_value["inventory_scope"]["course_groups"] += ("BPC",)
    changed = snapshot(
        inventory.rows[0].model_copy(
            update={
                "applicability": CourseApplicability(
                    status="explicit_groups", groups=("BPC",), source_locator=locator
                )
            }
        ),
        source_checksum=revision.checksum,
    )
    with pytest.raises(ScopedCatalogueError, match="source row|same source row"):
        materialize_catalogue(service, version, revision, changed)
    service.session.flush.assert_not_called()


@pytest.mark.parametrize("justification", [None, "", "Explicitly not a language subject"])
def test_inapplicability_requires_original_row_value_and_justification(
    justification: str | None,
) -> None:
    source = {"language_role": "not_applicable"}
    if justification is not None:
        source["not_applicable_justifications"] = {"language_role": justification}
    service, version, revision, inventory = bounded_inventory_context(source)
    service._source_metadata.return_value["inventory_scope"]["language_roles"] = ("not_applicable",)
    changed = snapshot(
        inventory.rows[0].model_copy(update={"language_role": "not_applicable"}),
        source_checksum=revision.checksum,
    )
    if justification:
        assert materialize_catalogue(service, version, revision, changed).status == "complete"
    else:
        with pytest.raises(ScopedCatalogueError, match="justification"):
            materialize_catalogue(service, version, revision, changed)
        service.session.flush.assert_not_called()


def test_global_reviewed_justification_cannot_override_actual_row_contradiction() -> None:
    service, version, revision, inventory = bounded_inventory_context()
    service._source_metadata.return_value["inventory_scope"]["language_roles"] += (
        "not_applicable",
    )
    service._source_metadata.return_value["not_applicable_justifications"] = {
        "language_role": "Review metadata cannot rewrite the original first-language row"
    }
    changed = snapshot(
        inventory.rows[0].model_copy(update={"language_role": "not_applicable"}),
        source_checksum=revision.checksum,
    )
    with pytest.raises(ScopedCatalogueError, match="contradicts language_role"):
        materialize_catalogue(service, version, revision, changed)


@pytest.mark.parametrize("dimension", ["pack_code", "version_code"])
def test_source_row_pack_version_cannot_be_rebound_by_global_scope(dimension: str) -> None:
    service, version, revision, inventory = bounded_inventory_context()
    if dimension == "pack_code":
        version.curriculum_pack.code = "other"
        service._source_metadata.return_value["inventory_scope"]["pack_code"] = "other"
    else:
        version.version_code = "other"
        service._source_metadata.return_value["inventory_scope"]["version_codes"] += ("other",)
    with pytest.raises(ScopedCatalogueError, match="source row contradicts pack/version"):
        materialize_catalogue(service, version, revision, inventory)
    service.session.flush.assert_not_called()


@pytest.mark.parametrize("mime", ["text/html", "application/pdf", "text/plain"])
def test_unsupported_row_association_formats_remain_blocked(mime: str) -> None:
    from app.curriculum_intelligence.scoped_catalogue import validate_catalogue_row_evidence

    service, version, revision, inventory = bounded_inventory_context()
    revision.content_type = mime
    with pytest.raises(ScopedCatalogueError, match="row-context adapter"):
        validate_catalogue_row_evidence(service, revision, inventory.rows[0], version=version)


@pytest.mark.parametrize("reason", [None, "This school resource has no course-group subdivision"])
def test_not_applicable_course_group_requires_explicit_original_justification(
    reason: str | None,
) -> None:
    source: dict[str, Any] = {
        "applicability": {"status": "explicit_groups", "groups": ["not_applicable"]}
    }
    if reason:
        source["not_applicable_justifications"] = {"course_group": reason}
    service, version, revision, inventory = bounded_inventory_context(source)
    service._source_metadata.return_value["inventory_scope"]["course_groups"] = ("not_applicable",)
    item = inventory.rows[0].model_copy(
        update={
            "applicability": CourseApplicability(
                status="explicit_groups",
                groups=("not_applicable",),
                source_locator="JSON pointer /inventory/0/applicability",
            )
        }
    )
    candidate = snapshot(item, source_checksum=revision.checksum)
    if reason:
        assert materialize_catalogue(service, version, revision, candidate).status == "complete"
    else:
        with pytest.raises(ScopedCatalogueError, match="inapplicability justification"):
            materialize_catalogue(service, version, revision, candidate)
