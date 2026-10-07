"""Offline simulated official lifecycles; these tests make no live-source claim."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.scoped_acceptance import (
    evaluate_day5_acceptance,
)
from app.curriculum_intelligence.scoped_catalogue import (
    CatalogueSnapshot,
    CourseApplicability,
    InventoryObservation,
    ScopedCatalogueRow,
    materialize_catalogue,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.curriculum import CurriculumNode, CurriculumVersion
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import CurriculumNodeSpec
from app.schemas.source_intelligence import SourceRegistrationInput
from app.repo_paths import curricula_content_dir
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

EXTRAS = {
    "course_family": "General",
    "course_group": "MPC",
    "subject_language": "English",
    "language_role": "not_applicable",
    "book_part": "whole",
    "bilingual": "no",
}


def _attach_frozen_manifest_contract(report: dict[str, Any], scope: dict[str, Any]) -> None:
    """Align offline acceptance fixtures with the frozen Day-5 manifest contract."""
    frozen_scope = json.loads(
        (curricula_content_dir() / "day5_scope.json").read_text(encoding="utf-8")
    )
    required = frozen_scope["frozen_required_academic_sources"]
    supplemental = frozen_scope["frozen_supplemental_authority_sources"]
    scope["frozen_required_academic_sources"] = required
    scope["frozen_supplemental_authority_sources"] = supplemental
    expected_required = len(required)
    expected_supplemental = len(supplemental)
    report["manifest_accounting"] = {
        "required_academic_expected_count": expected_required,
        "required_academic_count": expected_required,
        "required_academic_present_count": expected_required,
        "supplemental_authority_count": expected_supplemental,
        "manifest_validated_distinct": expected_required + expected_supplemental,
    }
    report.setdefault("manifest_identity_blockers", [])
    report.setdefault("manifest_classification_blockers", [])


def freeze_inventory(service, scope, item):
    version = service.session.get(CurriculumVersion, item["version_id"])
    revision = service.session.get(SourceRevision, item["source_revision_id"])
    snapshot = CatalogueSnapshot.model_validate(
        version.metadata_json["scoped_catalogue_snapshots"][revision.id]["snapshot"]
    )
    pack = {
        "code": item["pack_code"],
        "academic_version": version.version_code,
        "academic_year": version.academic_year,
        "grades": sorted({row.grade for row in snapshot.rows}),
        "inventories": [
            {
                "source_url": revision.metadata_json["source_snapshot"]["url"],
                "source_checksum": revision.checksum,
                "source_snapshot_checksum": revision.source_snapshot_checksum,
                "inventory_digest": snapshot.inventory_digest,
            }
        ],
    }
    scope["packs"] = [p for p in scope.get("packs", []) if p["code"] != pack["code"]] + [pack]


def _grade_row(row, grade, source_grades):
    locator = f"JSON pointer /catalogue/{source_grades.index(grade)}"
    return row.model_copy(
        update={
            "grade": grade,
            "source_locator": locator,
            "applicability": row.applicability.model_copy(
                update={"source_locator": locator + "/applicability"}
            ),
        }
    )


@pytest.fixture
def persisted(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        service = CurriculumIntelligenceService(
            session,
            source_service=SourceIntelligenceService(
                session, storage=LocalSourceStorage(tmp_path / "sources")
            ),
        )
        report: dict[str, Any] = {"materialized_slices": [], "catalogue_inventories": []}
        scope: dict[str, Any] = {"required_detailed_slices": []}
        source_grades = [
            "I",
            "II",
            "III",
            "IV",
            "V",
            "VI",
            "VII",
            "VIII",
            "IX",
            "X",
            "First Year",
            "Second Year",
        ]
        content = json.dumps(
            {
                "text": (
                    "I II III IV V VI VII VIII IX X First Year Second Year "
                    "English Science Unit Force Topic Concept SRC-L1 section 1"
                ),
                "grades": source_grades,
                "catalogue": [
                    {
                        "pack_code": "ts-scert" if index < 10 else "tgbie",
                        "version_code": "2025-26",
                        "official_label": "Science",
                        "grade": grade,
                        "academic_year": "2025-26",
                        "instructional_medium": "English",
                        "subject": "Science",
                        "subject_language": "English",
                        "language_role": "not_applicable",
                        "book_part": "whole",
                        "bilingual": "no",
                        "course_family": "General",
                        "resource_kind": "syllabus_document",
                        "applicability": {"status": "explicit_groups", "groups": ["MPC"]},
                        "not_applicable_justifications": {
                            "language_role": "Science is not a language course."
                        },
                    }
                    for index, grade in enumerate(source_grades)
                ],
            }
        ).encode()
        checksum = hashlib.sha256(content).hexdigest()
        for pack_code in ("ts-scert", "tgbie"):
            grades = (
                ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
                if pack_code == "ts-scert"
                else ["First Year", "Second Year"]
            )
            grade = "VIII" if pack_code == "ts-scert" else "First Year"
            row = ScopedCatalogueRow(
                pack_id="pending",
                version_id="pending",
                source_revision_id="pending",
                source_checksum=checksum,
                source_locator="JSON pointer /text",
                official_label="Science",
                subject="Science",
                grade=grade,
                academic_year="2025-26",
                instructional_medium="English",
                resource_kind="syllabus_document",
                course_family="General",
                subject_language="English",
                language_role="not_applicable",
                book_part="whole",
                bilingual="no",
                applicability=CourseApplicability(
                    status="explicit_groups", groups=("MPC",), source_locator="JSON pointer /text"
                ),
            )
            draft_snapshot = CatalogueSnapshot(
                source_revision_id="pending",
                source_checksum=checksum,
                rows=tuple(_grade_row(row, g, source_grades) for g in grades),
                inventory_observations=(
                    InventoryObservation(
                        source_locator=catalogue_row.source_locator,
                        status="resolved",
                        reason="reviewed inventory entry",
                        row_identity=catalogue_row.identity,
                    )
                    for catalogue_row in (_grade_row(row, g, source_grades) for g in grades)
                ),
                inventory_status="complete",
                extraction_method="reviewed offline test",
            )
            source = service.source_service.register_source(
                SourceRegistrationInput(
                    source_type=SourceType.OFFICIAL_SYLLABUS,
                    title="Offline source response",
                    url=f"https://example.invalid/{pack_code}.json",
                    authority="Offline authority",
                    country="India",
                    board_or_exam=pack_code,
                    academic_year="2025-26",
                    copyright_classification="test_response",
                    trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                    metadata_json={
                        "synthetic": False,
                        "document_type": "curriculum_index",
                        "official_catalogue_review_digests": [draft_snapshot.inventory_digest],
                        "verified_locators": [
                            "JSON pointer /text",
                            *(f"JSON pointer /grades/{source_grades.index(g)}" for g in grades),
                        ],
                        "curriculum_scope": {
                            "pack_code": pack_code,
                            "version_codes": ["2025-26"],
                            "grades": grades,
                            "media": ["English"],
                            "subjects": ["Science"],
                            "course_families": ["General"],
                            "course_groups": ["MPC"],
                            "subject_languages": ["English"],
                            "language_roles": ["not_applicable"],
                            "book_parts": ["whole"],
                            "bilingual_states": ["no"],
                            "publication_status": "final",
                            "applicability_status": "verified",
                            "applicability_locator": "JSON pointer /text",
                        },
                    },
                ),
                actor_id="test",
            )
            revision = service.source_service.ingest_upload(
                source.id,
                method=SourceIngestionMethod.JSON,
                filename="fixture.json",
                content=content,
                actor_id="test",
            )
            service.source_service.extract_revision(revision.id, actor_id="test")
            service.source_service.create_diff(revision.id, actor_id="test")
            assert service.source_service.validate_revision(revision.id, actor_id="test").valid
            service.source_service.approve_revision(revision.id, actor_id="test")
            service.source_service.activate_revision(revision.id, actor_id="test")
            pack = service.ensure_pack(
                framework=None,
                code=pack_code,
                name=pack_code,
                authority="Offline authority",
                country="India",
                revision=revision,
                source_locator="JSON pointer /text",
            )
            version = service.ensure_version(
                pack=pack,
                version_code="2025-26",
                academic_year="2025-26",
                revision=revision,
                active=False,
                source_locator="JSON pointer /text",
                metadata_json={"scope_enforced": True},
            )
            specs = []
            parent = None
            for node_type, title in zip(
                ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"),
                (grade, "English", "Science", "Unit", "Force", "Topic", "Concept"),
                strict=True,
            ):
                identity = {"grade": grade, "medium": "English", "subject": "Science", **EXTRAS}
                specs.append(
                    CurriculumNodeSpec(
                        node_type=node_type,
                        code=node_type,
                        title=title,
                        parent_code=parent,
                        official_text=title,
                        source_locator="JSON pointer /text",
                        metadata_json={
                            "identity": identity,
                            **({"official_code": "SRC-L1"} if node_type == "concept" else {}),
                        },
                    )
                )
                parent = node_type
            nodes = service.upsert_nodes(version=version, specs=specs, revision=revision)
            path = service.curriculum_path(nodes["concept"].id).model_dump(mode="json")
            scope["required_detailed_slices"].append(
                {
                    "key": pack_code,
                    "chapter": "Force",
                    "academic_version": "2025-26",
                    "source_revision": revision.id,
                    "source_checksum": revision.checksum,
                    "source_locator": "JSON pointer /text",
                    "pack_code": pack_code,
                    "grade": grade,
                    "medium": "English",
                    "subject": "Science",
                    **EXTRAS,
                }
            )
            report["materialized_slices"].append(
                {
                    "key": pack_code,
                    "source_revision_id": revision.id,
                    "source_checksum": revision.checksum,
                    "academic_version": "2025-26",
                    "synthetic": False,
                    "path": path,
                }
            )
            row = row.model_copy(
                update={
                    "pack_id": pack.id,
                    "version_id": version.id,
                    "source_revision_id": revision.id,
                    "source_checksum": revision.checksum,
                }
            )
            snapshot = CatalogueSnapshot(
                source_revision_id=revision.id,
                source_checksum=revision.checksum,
                rows=tuple(_grade_row(row, g, source_grades) for g in grades),
                inventory_observations=(
                    InventoryObservation(
                        source_locator=catalogue_row.source_locator,
                        status="resolved",
                        reason="reviewed inventory entry",
                        row_identity=catalogue_row.identity,
                    )
                    for catalogue_row in (_grade_row(row, g, source_grades) for g in grades)
                ),
                inventory_status="complete",
                extraction_method="reviewed offline test",
            )
            coverage = materialize_catalogue(service, version, revision, snapshot)
            report["catalogue_inventories"].append(
                {
                    "pack_code": pack_code,
                    "version_id": version.id,
                    "source_revision_id": revision.id,
                    "source_checksum": revision.checksum,
                    "snapshot_id": snapshot.identity,
                    "synthetic": False,
                    "inventory_kind": "official_catalogue",
                    "coverage": coverage.model_dump(mode="json"),
                }
            )
            freeze_inventory(service, scope, report["catalogue_inventories"][-1])
        _attach_frozen_manifest_contract(report, scope)
        session.commit()
        session.expunge_all()
        yield service, report, scope
    engine.dispose()


def test_positive_persisted_offline_fixture(persisted):
    service, report, scope = persisted
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert result["passed"], result
    assert result["verified_detailed_slice_count"] == 2
    assert not evaluate_day5_acceptance(report, scope)["passed"]


@pytest.mark.parametrize(
    "attack",
    [
        "ids",
        "version",
        "checksum",
        "locator",
        "duplicate",
        "missing",
        "blocked",
        "exclude",
        "unfreeze",
        "inventory_kind",
        "inventory_duplicate",
        "applicability",
        "catalogue_gaps",
        "fetch_blockers",
        "synthetic",
        "bytes",
        "catalogue_rows",
    ],
)
def test_forged_report_or_persisted_evidence_fails(persisted, attack):
    service, original, original_scope = persisted
    report, scope = copy.deepcopy(original), copy.deepcopy(original_scope)
    item = report["materialized_slices"][0]
    required = scope["required_detailed_slices"][0]
    verification = None
    if attack == "ids":
        item["path"]["node_ids"] = [f"nonexistent-{n}" for n in range(7)]
    elif attack == "version":
        item["academic_version"] = "2026-27"
    elif attack == "checksum":
        item["source_checksum"] = "f" * 64
    elif attack == "locator":
        node = service.session.get(CurriculumNode, item["path"]["node_ids"][-1])
        node.source_locator = "forged page"
    elif attack == "duplicate":
        report["materialized_slices"].append(copy.deepcopy(item))
    elif attack == "missing":
        report["materialized_slices"].pop()
    elif attack == "blocked":
        required["status"] = "blocked"
    elif attack == "exclude":
        verification = {"blocked_slice_keys": [required["key"]]}
    elif attack == "unfreeze":
        required["source_revision"] = None
    elif attack == "inventory_kind":
        report["catalogue_inventories"][0]["inventory_kind"] = "detailed_slice"
    elif attack == "inventory_duplicate":
        report["catalogue_inventories"].append(copy.deepcopy(report["catalogue_inventories"][0]))
    elif attack == "applicability":
        report["unresolved_applicability"] = ["missing notice"]
    elif attack in {"catalogue_gaps", "fetch_blockers"}:
        report[attack] = ["blocked"]
    elif attack == "synthetic":
        item["synthetic"] = True
    elif attack == "bytes":
        revision = service.session.get(SourceRevision, item["source_revision_id"])
        service.source_service.storage.root.joinpath(revision.storage_path).write_bytes(b"tampered")
    elif attack == "catalogue_rows":
        inventory = report["catalogue_inventories"][0]
        version = service.session.get(CurriculumVersion, inventory["version_id"])
        metadata = copy.deepcopy(version.metadata_json)
        metadata["scoped_catalogue_snapshots"][inventory["source_revision_id"]]["rows"] = []
        version.metadata_json = metadata
    for evidence in report["materialized_slices"]:
        evidence.update(
            {
                "verified_from_persisted_entities": True,
                "exact_bytes_verified": True,
                "source_domain_verified": True,
                "locator_verified": True,
                "applicability_verified": True,
                "status": "verified",
            }
        )
    result = evaluate_day5_acceptance(
        report, scope, service=service, verification_slice=verification
    )
    assert not result["passed"], attack


def test_stable_reviewed_binding_replays_in_fresh_database(persisted, tmp_path):
    first_service, _, frozen = persisted
    frozen = copy.deepcopy(frozen)
    for required in frozen["required_detailed_slices"]:
        revision = first_service.session.get(SourceRevision, required.pop("source_revision"))
        required["source_url"] = revision.metadata_json["source_snapshot"]["url"]
        required["source_snapshot_checksum"] = revision.source_snapshot_checksum
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    # A second complete offline lifecycle uses different database-generated revision UUIDs.
    replay = globals()["persisted"].__wrapped__(fresh)
    service, report, _ = next(replay)
    try:
        assert evaluate_day5_acceptance(report, frozen, service=service)["passed"]
        frozen["required_detailed_slices"][0]["source_snapshot_checksum"] = "f" * 64
        assert not evaluate_day5_acceptance(report, frozen, service=service)["passed"]
    finally:
        replay.close()


def test_frozen_catalogue_grade_boundary_cannot_be_shrunk(persisted):
    service, report, scope = persisted
    scope["packs"][0]["grades"] = ["VIII", "XI"]
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue_scope" in result["incomplete_components"]


def draft_inventory(
    service, report, *, binding_year="2025-26", row_overrides=None, governing_grades=None
):
    """Approve a distinct draft inventory without changing its final governing source."""
    inventory = report["catalogue_inventories"][0]
    version = service.session.get(CurriculumVersion, inventory["version_id"])
    governing = service.session.get(SourceRevision, version.source_revision_id)
    original = CatalogueSnapshot.model_validate(
        version.metadata_json["scoped_catalogue_snapshots"][governing.id]["snapshot"]
    )
    draft_payload = json.loads(service.source_service.storage.read(governing.storage_path))
    if row_overrides:
        row_overrides = dict(row_overrides)
        if "applicability" in row_overrides:
            row_overrides["applicability"] = row_overrides["applicability"].model_copy(
                update={"source_locator": original.rows[0].source_locator + "/applicability"}
            )
        for field, value in row_overrides.items():
            draft_payload["catalogue"][0][field] = (
                value.model_dump(mode="json", exclude={"source_locator"})
                if field == "applicability"
                else value
            )
    draft_content = json.dumps(draft_payload).encode()
    draft_checksum = hashlib.sha256(draft_content).hexdigest()
    changed_rows = tuple(
        row.model_copy(
            update={
                **(row_overrides if row_overrides and index == 0 else {}),
                "source_checksum": draft_checksum,
            }
        )
        for index, row in enumerate(original.rows)
    )
    original = CatalogueSnapshot(
        source_revision_id=original.source_revision_id,
        source_checksum=draft_checksum,
        rows=changed_rows,
        inventory_status="complete",
        extraction_method=original.extraction_method,
        inventory_observations=tuple(
            InventoryObservation(
                source_locator=row.source_locator,
                status="resolved",
                reason="reviewed inventory entry",
                row_identity=row.identity,
            )
            for row in changed_rows
        ),
    )
    metadata = copy.deepcopy(service._source_metadata(governing))
    metadata["inventory_scope"] = metadata.pop("curriculum_scope")
    metadata["official_catalogue_review_digests"] = [original.inventory_digest]
    metadata["inventory_scope"]["publication_status"] = "draft"
    if row_overrides:
        for field, allowed in {
            "grade": "grades",
            "instructional_medium": "media",
            "subject": "subjects",
            "course_family": "course_families",
            "subject_language": "subject_languages",
            "language_role": "language_roles",
            "book_part": "book_parts",
            "bilingual": "bilingual_states",
        }.items():
            if field in row_overrides and row_overrides[field] != "unknown":
                metadata["inventory_scope"][allowed] = [
                    *metadata["inventory_scope"].get(allowed, []),
                    row_overrides[field],
                ]
    if row_overrides and "applicability" in row_overrides:
        metadata["inventory_scope"]["course_groups"] = [
            *metadata["inventory_scope"].get("course_groups", []),
            *row_overrides["applicability"].groups,
        ]
    metadata["document_type"] = "textbook_index"
    if governing_grades is not None:
        governing_metadata = copy.deepcopy(service._source_metadata(governing))
        governing_metadata["curriculum_scope"]["grades"] = governing_grades
        narrow_source = service.source_service.register_source(
            SourceRegistrationInput(
                source_type=SourceType.OFFICIAL_SYLLABUS,
                title="Offline narrow governing source",
                url="https://example.invalid/narrow-governing.json",
                authority="Offline authority",
                country="India",
                board_or_exam="ts-scert",
                academic_year="2025-26",
                copyright_classification="test_response",
                trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                metadata_json=governing_metadata,
            ),
            actor_id="test",
        )
        narrower = service.source_service.ingest_upload(
            narrow_source.id,
            method=SourceIngestionMethod.JSON,
            filename="narrow.json",
            content=service.source_service.storage.read(governing.storage_path),
            actor_id="test",
        )
        service.source_service.extract_revision(narrower.id, actor_id="test")
        service.source_service.create_diff(narrower.id, actor_id="test")
        assert service.source_service.validate_revision(narrower.id, actor_id="test").valid
        service.source_service.approve_revision(narrower.id, actor_id="test")
        service.source_service.activate_revision(narrower.id, actor_id="test")
        governing = narrower
        version.source_revision_id = governing.id
    metadata["governing_source"] = {
        "source_url": governing.metadata_json["source_snapshot"]["url"],
        "source_checksum": governing.checksum,
        "source_snapshot_checksum": governing.source_snapshot_checksum,
        "academic_year": binding_year,
        "version_code": version.version_code,
    }
    source = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="Offline draft textbook inventory",
            url="https://example.invalid/draft-inventory.json",
            authority="Offline authority",
            country="India",
            board_or_exam="ts-scert",
            academic_year="2025-26",
            copyright_classification="test_response",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json=metadata,
        ),
        actor_id="test",
    )
    revision = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="draft.json",
        content=draft_content,
        actor_id="test",
    )
    service.source_service.extract_revision(revision.id, actor_id="test")
    service.source_service.create_diff(revision.id, actor_id="test")
    assert service.source_service.validate_revision(revision.id, actor_id="test").valid
    service.source_service.approve_revision(revision.id, actor_id="test")
    service.source_service.activate_revision(revision.id, actor_id="test")
    rows = tuple(
        row.model_copy(update={"source_revision_id": revision.id}) for row in original.rows
    )
    snapshot = CatalogueSnapshot(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        rows=rows,
        inventory_status="complete",
        extraction_method=original.extraction_method,
        inventory_observations=tuple(
            InventoryObservation(
                source_locator=row.source_locator,
                status="resolved",
                reason="reviewed inventory entry",
                row_identity=row.identity,
            )
            for row in rows
        ),
    )
    coverage = materialize_catalogue(service, version, revision, snapshot)
    inventory.update(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        snapshot_id=snapshot.identity,
        coverage=coverage.model_dump(mode="json"),
    )
    return version, revision


def test_draft_catalogue_is_accounted_without_promoting_publication(persisted):
    service, report, scope = persisted
    version, revision = draft_inventory(service, report)
    freeze_inventory(service, scope, report["catalogue_inventories"][0])
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert result["passed"], result
    assert service._source_metadata(revision)["inventory_scope"]["publication_status"] == "draft"
    assert version.source_revision_id != revision.id
    assert version.status == "draft"


@pytest.mark.parametrize("attack", ["draft_alone", "wrong_year"])
def test_draft_catalogue_requires_distinct_final_same_year_governing_evidence(persisted, attack):
    service, report, scope = persisted
    version, revision = draft_inventory(
        service, report, binding_year="2026-27" if attack == "wrong_year" else "2025-26"
    )
    freeze_inventory(service, scope, report["catalogue_inventories"][0])
    if attack == "draft_alone":
        version.source_revision_id = revision.id
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue" in result["incomplete_components"]


@pytest.mark.parametrize(
    "attack",
    [
        "absent",
        "null_version",
        "wrong_version",
        "wrong_year",
        "missing_binding",
        "wrong_url",
        "wrong_checksum",
        "wrong_snapshot",
        "wrong_digest",
        "duplicate",
        "unexpected",
    ],
)
def test_catalogue_requires_independently_frozen_scope(persisted, attack):
    service, report, scope = persisted
    pack = scope["packs"][0]
    expected = pack["inventories"][0]
    if attack == "absent":
        scope.pop("packs")
    elif attack == "null_version":
        pack["academic_version"] = None
    elif attack == "wrong_version":
        pack["academic_version"] = "2026-27"
    elif attack == "wrong_year":
        pack["academic_year"] = "2026-27"
    elif attack == "missing_binding":
        pack["inventories"] = []
    elif attack.startswith("wrong_"):
        key = {
            "wrong_url": "source_url",
            "wrong_checksum": "source_checksum",
            "wrong_snapshot": "source_snapshot_checksum",
            "wrong_digest": "inventory_digest",
        }[attack]
        expected[key] = "forged"
    elif attack == "duplicate":
        pack["inventories"].append(copy.deepcopy(expected))
    elif attack == "unexpected":
        scope["packs"].pop()
    assert not evaluate_day5_acceptance(report, scope, service=service)["passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("grade", "XI"),
        ("instructional_medium", "Telugu"),
        ("subject", "Mathematics"),
        ("course_family", "Vocational"),
        ("subject_language", "Telugu"),
        ("language_role", "first"),
        ("book_part", "Part 2"),
        ("bilingual", "yes"),
        (
            "applicability",
            CourseApplicability(
                status="explicit_groups", groups=("MEC",), source_locator="JSON pointer /text"
            ),
        ),
    ],
)
def test_draft_inventory_cannot_expand_governing_dimensions(persisted, field, value):
    service, report, scope = persisted
    draft_inventory(service, report, row_overrides={field: value})
    freeze_inventory(service, scope, report["catalogue_inventories"][0])
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue" in result["incomplete_components"]


@pytest.mark.parametrize("field", list(EXTRAS))
def test_detailed_path_requires_each_frozen_extra_dimension(persisted, field):
    service, report, scope = persisted
    scope["required_detailed_slices"][0][field] = "different"
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert" in result["incomplete_components"]


def test_class_viii_governing_source_cannot_authorize_i_to_x_draft_inventory(persisted):
    service, report, scope = persisted
    draft_inventory(service, report, governing_grades=["VIII"])
    freeze_inventory(service, scope, report["catalogue_inventories"][0])
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue" in result["incomplete_components"]


@pytest.mark.parametrize("level", range(7))
@pytest.mark.parametrize("field", ["grade", "medium", "subject", *EXTRAS])
@pytest.mark.parametrize("attack", ["omit", "conflict"])
def test_all_persisted_path_levels_match_frozen_applicability(persisted, level, field, attack):
    service, report, scope = persisted
    node_id = report["materialized_slices"][0]["path"]["node_ids"][level]
    node = service.session.get(CurriculumNode, node_id)
    metadata = copy.deepcopy(node.metadata_json)
    if attack == "omit":
        metadata["identity"].pop(field)
    else:
        metadata["identity"][field] = "forged"
    node.metadata_json = metadata
    service.session.flush()
    service.session.expire_all()
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert" in result["incomplete_components"]


@pytest.mark.parametrize("level", range(7))
@pytest.mark.parametrize("field", ["grade", "medium", "subject", *EXTRAS])
@pytest.mark.parametrize("attack", ["omit", "conflict"])
def test_generic_writer_requires_applicability_on_every_level_and_rolls_back(
    persisted, level, field, attack
):
    from sqlalchemy import select

    service, report, _ = persisted
    item = report["materialized_slices"][0]
    nodes = service.hierarchy_path(item["path"]["node_ids"][-1])
    revision = service.session.get(SourceRevision, item["source_revision_id"])
    specs = []
    parent = None
    for index, node in enumerate(nodes):
        metadata = copy.deepcopy(node.metadata_json)
        if index == level:
            if attack == "omit":
                metadata["identity"].pop(field)
            else:
                # IX is a valid reviewed grade, but it cannot join this VIII path.
                metadata["identity"][field] = "IX" if field == "grade" else "forged"
        code = "new-" + node.node_type
        specs.append(
            CurriculumNodeSpec(
                node_type=node.node_type,
                code=code,
                title=node.title,
                parent_code=parent,
                official_text=node.official_text,
                source_locator=node.source_locator,
                metadata_json=metadata,
            )
        )
        parent = code
    with pytest.raises(
        ValueError,
        match="requires source-declared|does not establish exact|Hierarchy crosses parent",
    ):
        with service.session.begin_nested():
            service.upsert_nodes(
                version=nodes[-1].curriculum_version, revision=revision, specs=specs
            )
    assert not list(
        service.session.scalars(select(CurriculumNode).where(CurriculumNode.code.like("new-%")))
    )
    assert len(service.hierarchy_path(item["path"]["node_ids"][-1])) == 7


@pytest.mark.parametrize("field", list(EXTRAS))
@pytest.mark.parametrize("unverified", ["unknown", "not_applicable"])
def test_generic_hierarchy_does_not_invent_non_applicability(persisted, field, unverified):
    service, report, _ = persisted
    item = report["materialized_slices"][0]
    root = service.session.get(CurriculumNode, item["path"]["node_ids"][0])
    revision = service.session.get(SourceRevision, item["source_revision_id"])
    metadata = copy.deepcopy(root.metadata_json)
    metadata["identity"][field] = unverified
    spec = CurriculumNodeSpec(
        node_type="grade_year",
        code="unreviewed-root",
        title=root.title,
        official_text=root.official_text,
        source_locator=root.source_locator,
        metadata_json=metadata,
    )
    if EXTRAS[field] == unverified:
        # The fixture explicitly declares not_applicable for language_role.
        nodes = service.upsert_nodes(
            version=root.curriculum_version, revision=revision, specs=[spec]
        )
        assert nodes["unreviewed-root"].metadata_json["identity"][field] == unverified
        return
    with pytest.raises(ValueError, match="requires source-declared .* applicability"):
        with service.session.begin_nested():
            service.upsert_nodes(version=root.curriculum_version, revision=revision, specs=[spec])


@pytest.mark.parametrize("field", ["grade", "medium", "subject", *EXTRAS])
def test_generic_writer_rejects_incomplete_existing_parent(persisted, field):
    service, report, _ = persisted
    item = report["materialized_slices"][0]
    nodes = service.hierarchy_path(item["path"]["node_ids"][-1])
    root, medium = nodes[:2]
    metadata = copy.deepcopy(root.metadata_json)
    metadata["identity"].pop(field)
    root.metadata_json = metadata
    service.session.flush()
    spec = CurriculumNodeSpec(
        node_type="medium",
        code="new-medium",
        title=medium.title,
        parent_code=root.code,
        official_text=medium.official_text,
        source_locator=medium.source_locator,
        metadata_json=copy.deepcopy(medium.metadata_json),
    )
    revision = service.session.get(SourceRevision, item["source_revision_id"])
    with pytest.raises(ValueError, match="Hierarchy parent requires source-declared"):
        service.upsert_nodes(version=root.curriculum_version, revision=revision, specs=[spec])


@pytest.mark.parametrize("ancestor_level", [0, 3])
@pytest.mark.parametrize("field", ["grade", "medium", "subject", *EXTRAS])
@pytest.mark.parametrize("attack", ["omit", "conflict"])
def test_writer_cannot_extend_valid_parent_with_corrupt_older_ancestor(
    persisted, ancestor_level, field, attack
):
    from sqlalchemy import select

    service, report, _ = persisted
    item = report["materialized_slices"][0]
    nodes = service.hierarchy_path(item["path"]["node_ids"][-1])
    ancestor, parent, concept = nodes[ancestor_level], nodes[-2], nodes[-1]
    good_identity = {"identity": copy.deepcopy(concept.metadata_json["identity"])}
    metadata = copy.deepcopy(ancestor.metadata_json)
    if attack == "omit":
        metadata["identity"].pop(field)
    else:
        metadata["identity"][field] = "IX" if field == "grade" else "forged"
    ancestor.metadata_json = metadata
    service.session.flush()
    assert parent.metadata_json == good_identity
    prefix = CurriculumNodeSpec(
        node_type="grade_year",
        code="prefix-root",
        title=nodes[0].title,
        official_text=nodes[0].official_text,
        source_locator=nodes[0].source_locator,
        metadata_json=good_identity,
    )
    extension = CurriculumNodeSpec(
        node_type="concept",
        code="extension-concept",
        title=concept.title,
        parent_code=parent.code,
        official_text=concept.official_text,
        source_locator=concept.source_locator,
        metadata_json=good_identity,
    )
    revision = service.session.get(SourceRevision, item["source_revision_id"])
    with pytest.raises(ValueError, match="scope|applicability|identity"):
        service.upsert_nodes(
            version=concept.curriculum_version, revision=revision, specs=[prefix, extension]
        )
    assert not list(
        service.session.scalars(
            select(CurriculumNode).where(
                CurriculumNode.code.in_(["prefix-root", "extension-concept"])
            )
        )
    )
    # Verification constrains new writes, not the read-only historical traversal API.
    assert len(service.curriculum_path(concept.id).node_ids) == 7


def section_revision(
    service, version, domain, *, synthetic=False, applicability_locator="JSON pointer /sections/A"
):
    governing = service.session.get(SourceRevision, version.source_revision_id)
    metadata = copy.deepcopy(service._source_metadata(governing))
    metadata.update(
        document_type=domain,
        synthetic=synthetic,
        verified_locators=["JSON pointer /sections/A", "JSON pointer /sections/B"],
    )
    metadata["curriculum_scope"]["applicability_locator"] = applicability_locator
    metadata["verified_locators"].append(applicability_locator)
    source = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="Offline bounded statements",
            url=f"https://example.invalid/sections-{domain}.json",
            authority="Offline authority",
            country="India",
            board_or_exam=version.curriculum_pack.code,
            academic_year=version.academic_year,
            copyright_classification="test_response",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json=metadata,
        ),
        actor_id="test",
    )
    revision = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="sections.json",
        actor_id="test",
        content=json.dumps(
            {
                "sections": {
                    "A": {"code": "OUT-A1", "text": "Statement within section A."},
                    "B": {"code": "OUT-B1", "text": "Statement within section B."},
                }
            }
        ).encode(),
    )
    service.source_service.extract_revision(revision.id, actor_id="test")
    service.source_service.create_diff(revision.id, actor_id="test")
    assert service.source_service.validate_revision(revision.id, actor_id="test").valid
    service.source_service.approve_revision(revision.id, actor_id="test")
    service.source_service.activate_revision(revision.id, actor_id="test")
    return revision


def write_statement(
    service,
    version,
    revision,
    kind,
    *,
    text="Statement within section A.",
    code="OUT-A1",
    locator="JSON pointer /sections/A",
):
    from app.schemas.curriculum_intelligence import CompetencySpec, LearningOutcomeSpec

    metadata = {
        "identity": {"grade": "VIII", "medium": "English", "subject": "Science", **EXTRAS},
        "official_code": code,
    }
    if kind == "outcome":
        return service.upsert_learning_outcomes(
            version=version,
            revision=revision,
            specs=[
                LearningOutcomeSpec(
                    code="bounded-outcome",
                    text=text,
                    source_locator=locator,
                    metadata_json=metadata,
                )
            ],
        )["bounded-outcome"]
    return service.upsert_competencies(
        framework=None,
        curriculum_version=version,
        revision=revision,
        specs=[
            CompetencySpec(
                code="bounded-standard",
                name="Bounded standard",
                official_text=text,
                source_locator=locator,
                metadata_json=metadata,
            )
        ],
    )["bounded-standard"]


@pytest.mark.parametrize("kind", ["outcome", "standard"])
@pytest.mark.parametrize("scoped", [True, False])
@pytest.mark.parametrize("synthetic", [True, False])
@pytest.mark.parametrize(
    "attack", ["wrong_section", "wrong_code", "code_prefix", "missing_locator"]
)
def test_statement_writers_require_bounded_wording_for_all_argument_modes(
    persisted, kind, scoped, synthetic, attack
):
    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    version.metadata_json = {**version.metadata_json, "scope_enforced": scoped}
    domain = "learning_outcomes" if kind == "outcome" else "academic_standard"
    revision = section_revision(service, version, domain, synthetic=synthetic)
    kwargs = {}
    if attack == "wrong_section":
        kwargs["text"] = "Statement within section B."
    elif attack == "wrong_code":
        kwargs["code"] = "OUT-B1"
    elif attack == "code_prefix":
        kwargs["code"] = "OUT-A"
    else:
        kwargs["locator"] = ""
    with pytest.raises(ValueError):
        write_statement(service, version, revision, kind, **kwargs)


@pytest.mark.parametrize("kind", ["outcome", "standard"])
@pytest.mark.parametrize("attack", [None, "wrong_section", "wrong_code", "code_prefix"])
def test_persisted_statement_acceptance_rechecks_exact_bounded_evidence(persisted, kind, attack):
    from app.curriculum_intelligence.scoped_acceptance import _verify_slice

    service, report, scope = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(
        service, version, "learning_outcomes" if kind == "outcome" else "academic_standard"
    )
    entity = write_statement(service, version, revision, kind)
    if attack == "wrong_section":
        if kind == "outcome":
            entity.text = "Statement within section B."
        else:
            entity.official_text = "Statement within section B."
    elif attack:
        entity.metadata_json = {
            **entity.metadata_json,
            "official_code": "OUT-B1" if attack == "wrong_code" else "OUT-A",
        }
    service.session.flush()
    service.session.expire_all()
    expected = {
        **scope["required_detailed_slices"][0],
        "key": "scert-learning-outcomes" if kind == "outcome" else "scert-academic-standards",
        "source_revision": revision.id,
        "source_checksum": revision.checksum,
        "source_locator": "JSON pointer /sections/A",
    }
    observation = {
        "synthetic": False,
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": version.version_code,
        "persisted_entity_ids": [entity.id],
    }
    if attack:
        with pytest.raises(ValueError):
            _verify_slice(service, expected, observation)
    else:
        assert _verify_slice(service, expected, observation)


def section_path_specs():
    specs = []
    parent = None
    for kind in ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"):
        specs.append(
            CurriculumNodeSpec(
                node_type=kind,
                code="bounded-" + kind,
                parent_code=parent,
                title="Selected " + kind,
                official_text="Statement within section A."
                if kind in {"chapter", "topic"}
                else None,
                source_locator="JSON pointer /sections/A",
                metadata_json={
                    "identity": {
                        "grade": "VIII",
                        "medium": "English",
                        "subject": "Science",
                        **EXTRAS,
                    },
                    "label_status": "official" if kind in {"chapter", "topic"} else "derived",
                },
            )
        )
        parent = "bounded-" + kind
    return specs


@pytest.mark.parametrize("level", range(7))
def test_scoped_node_writer_binds_every_claimed_quote_to_locator(persisted, level):
    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(service, version, "syllabus")
    specs = section_path_specs()
    specs[level] = specs[level].model_copy(update={"official_text": "Statement within section B."})
    with pytest.raises(ValueError, match="absent at exact locator"):
        service.upsert_nodes(version=version, revision=revision, specs=specs)


@pytest.mark.parametrize(
    "attack", [None, "chapter_absent", "topic_absent", "concept_unlabelled", *range(7)]
)
def test_detailed_acceptance_rechecks_bounded_node_quotes_and_derived_labels(persisted, attack):
    from app.curriculum_intelligence.scoped_acceptance import _verify_slice

    service, report, scope = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(service, version, "syllabus")
    specs = section_path_specs()
    nodes = service.upsert_nodes(version=version, revision=revision, specs=specs)
    if isinstance(attack, int):
        nodes[specs[attack].code].official_text = "Statement within section B."
    elif attack in {"chapter_absent", "topic_absent"}:
        nodes["bounded-" + attack.split("_")[0]].official_text = None
    elif attack == "concept_unlabelled":
        node = nodes["bounded-concept"]
        node.metadata_json = {"identity": node.metadata_json["identity"]}
    service.session.flush()
    expected = {
        **scope["required_detailed_slices"][0],
        "chapter": "Selected chapter",
        "source_revision": revision.id,
        "source_checksum": revision.checksum,
        "source_locator": "JSON pointer /sections/A",
    }
    observation = {
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": version.version_code,
        "synthetic": False,
        "path": service.curriculum_path(nodes["bounded-concept"].id).model_dump(mode="json"),
    }
    if isinstance(attack, int):
        with pytest.raises(ValueError, match="absent at exact locator"):
            _verify_slice(service, expected, observation)
    else:
        assert _verify_slice(service, expected, observation) is (attack is None)


@pytest.mark.parametrize("kind", ["outcome", "standard"])
def test_bounded_statement_failure_rolls_back_valid_batch_prefix(persisted, kind):
    from sqlalchemy import select

    from app.models.curriculum import Competency, LearningOutcome
    from app.schemas.curriculum_intelligence import CompetencySpec, LearningOutcomeSpec

    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(service, version, "syllabus")
    metadata = {"identity": {"grade": "VIII", "medium": "English", "subject": "Science", **EXTRAS}}
    with pytest.raises(ValueError, match="absent at exact locator"):
        if kind == "outcome":
            specs = [
                LearningOutcomeSpec(
                    code="prefix-" + label,
                    text=f"Statement within section {label}.",
                    source_locator="JSON pointer /sections/A",
                    metadata_json=metadata,
                )
                for label in ("A", "B")
            ]
            service.upsert_learning_outcomes(version=version, revision=revision, specs=specs)
        else:
            specs = [
                CompetencySpec(
                    code="prefix-" + label,
                    name="Standard " + label,
                    official_text=f"Statement within section {label}.",
                    source_locator="JSON pointer /sections/A",
                    metadata_json=metadata,
                )
                for label in ("A", "B")
            ]
            service.upsert_competencies(
                framework=None, curriculum_version=version, revision=revision, specs=specs
            )
    model = LearningOutcome if kind == "outcome" else Competency
    assert not list(service.session.scalars(select(model).where(model.code.like("prefix-%"))))


def test_approved_metadata_cannot_invent_applicability_location(persisted):
    from app.curriculum_intelligence.scoped_curriculum import validate_version_scope

    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(
        service, version, "syllabus", applicability_locator="JSON pointer /invented"
    )
    with pytest.raises(ValueError, match="Source location unavailable"):
        validate_version_scope(
            service,
            revision,
            pack_code=version.curriculum_pack.code,
            version_code=version.version_code,
            active=True,
        )
    with pytest.raises(ValueError, match="Source location unavailable"):
        service.upsert_nodes(version=version, revision=revision, specs=section_path_specs())


def test_approved_locator_whitelist_does_not_substitute_for_actual_location(persisted):
    from app.curriculum_intelligence.scoped_acceptance import _locator

    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(
        service, version, "syllabus", applicability_locator="JSON pointer /invented"
    )
    assert "JSON pointer /invented" in service._source_metadata(revision)["verified_locators"]
    assert not _locator(service, revision, "JSON pointer /invented")
    assert _locator(service, revision, "JSON pointer /sections/A")


@pytest.mark.parametrize("remove_approval", [False, True])
def test_unscoped_outcome_cannot_launder_source_domain_by_corrupting_snapshot(
    persisted, remove_approval
):
    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    version.metadata_json = {**version.metadata_json, "scope_enforced": False}
    revision = section_revision(service, version, "learning_outcomes")
    metadata = copy.deepcopy(revision.metadata_json)
    metadata["source_snapshot"]["metadata_json"].pop("document_type")
    metadata["source_snapshot"]["metadata_json"]["synthetic"] = True
    revision.metadata_json = metadata
    if remove_approval:
        revision.approval_fingerprint = None
    with pytest.raises(ValueError, match="Outcome source approval integrity mismatch"):
        write_statement(service, version, revision, "outcome", text="Statement within section B.")


@pytest.mark.parametrize("code", ["OUT-A1", "OUT-B1", "OUT-A", ""])
def test_code_only_scoped_node_claim_requires_actual_bounded_identifier(persisted, code):
    service, report, _ = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(service, version, "syllabus")
    specs = section_path_specs()
    specs[-1] = specs[-1].model_copy(
        update={"metadata_json": {**specs[-1].metadata_json, "official_code": code}}
    )
    if code == "OUT-A1":
        assert (
            service.upsert_nodes(version=version, revision=revision, specs=specs)[
                "bounded-concept"
            ].official_text
            is None
        )
    else:
        with pytest.raises(ValueError):
            service.upsert_nodes(version=version, revision=revision, specs=specs)


@pytest.mark.parametrize("code", ["OUT-A1", "OUT-B1", "OUT-A"])
def test_code_only_existing_ancestor_and_acceptance_recheck_claim(persisted, code):
    from app.curriculum_intelligence.scoped_acceptance import _verify_slice

    service, report, scope = persisted
    version = service.session.get(
        CurriculumVersion, report["catalogue_inventories"][0]["version_id"]
    )
    revision = section_revision(service, version, "syllabus")
    nodes = service.upsert_nodes(version=version, revision=revision, specs=section_path_specs())
    root = nodes["bounded-grade_year"]
    root.metadata_json = {**root.metadata_json, "official_code": code}
    service.session.flush()
    expected = {
        **scope["required_detailed_slices"][0],
        "chapter": "Selected chapter",
        "source_revision": revision.id,
        "source_checksum": revision.checksum,
        "source_locator": "JSON pointer /sections/A",
    }
    observation = {
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": version.version_code,
        "synthetic": False,
        "path": service.curriculum_path(nodes["bounded-concept"].id).model_dump(mode="json"),
    }
    spec = section_path_specs()[-1].model_copy(update={"code": "extra-concept"})
    if code == "OUT-A1":
        assert _verify_slice(service, expected, observation)
        assert service.upsert_nodes(version=version, revision=revision, specs=[spec])[
            "extra-concept"
        ]
    else:
        with pytest.raises(ValueError):
            _verify_slice(service, expected, observation)
        with pytest.raises(ValueError):
            service.upsert_nodes(version=version, revision=revision, specs=[spec])


def pair_revision(
    service, version, name, media, content, declarations=(), *, alignments=(), scope_overrides=None
):
    original = service.session.get(SourceRevision, version.source_revision_id)
    metadata = copy.deepcopy(service._source_metadata(original))
    metadata.update(
        document_type="syllabus",
        correspondences=list(declarations),
        direct_alignments=list(alignments),
    )
    metadata["curriculum_scope"]["media"] = media
    metadata["curriculum_scope"].update(scope_overrides or {})
    metadata["curriculum_scope"]["applicability_locator"] = "JSON pointer /text"
    source = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="Offline paired source",
            url=f"https://example.invalid/{name}.json",
            authority="Offline authority",
            country="India",
            board_or_exam=version.curriculum_pack.code,
            academic_year=version.academic_year,
            copyright_classification="test_response",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json=metadata,
        ),
        actor_id="test",
    )
    revision = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="pair.json",
        content=json.dumps(content, ensure_ascii=False).encode(),
        actor_id="test",
    )
    service.source_service.extract_revision(revision.id, actor_id="test")
    service.source_service.create_diff(revision.id, actor_id="test")
    assert service.source_service.validate_revision(revision.id, actor_id="test").valid
    service.source_service.approve_revision(revision.id, actor_id="test")
    service.source_service.activate_revision(revision.id, actor_id="test")
    return revision


@pytest.fixture
def paired(persisted):
    return _paired_case(persisted)


def _paired_case(persisted, shared=False):
    from app.curriculum_intelligence.scoped_curriculum import link_correspondence

    service, report, scope = persisted
    left_observed = copy.deepcopy(report["materialized_slices"][0])
    left_expected = copy.deepcopy(scope["required_detailed_slices"][0])
    version = service.session.get(CurriculumVersion, left_observed["path"]["curriculum_version_id"])
    if shared:
        left_revision = pair_revision(
            service,
            version,
            "shared-left",
            ["English"],
            {
                "text": "VIII English Science Unit Force Topic",
                "concept": {"code": "SRC-L1", "text": "Shared"},
            },
        )
        left_specs = []
        parent = None
        for kind, title in zip(
            ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"),
            ("VIII", "English", "Science", "Unit", "Force", "Topic", "Shared"),
            strict=True,
        ):
            code = "shared-left-" + kind
            left_specs.append(
                CurriculumNodeSpec(
                    node_type=kind,
                    code=code,
                    title=title,
                    parent_code=parent,
                    official_text=title,
                    source_locator="JSON pointer /concept"
                    if kind == "concept"
                    else "JSON pointer /text",
                    metadata_json={
                        "identity": {
                            "grade": "VIII",
                            "medium": "English",
                            "subject": "Science",
                            **EXTRAS,
                        },
                        **({"official_code": "SRC-L1"} if kind == "concept" else {}),
                    },
                )
            )
            parent = code
        left_nodes = service.upsert_nodes(version=version, revision=left_revision, specs=left_specs)
        left_observed = {
            **left_observed,
            "source_revision_id": left_revision.id,
            "source_checksum": left_revision.checksum,
            "path": service.curriculum_path(left_nodes["shared-left-concept"].id).model_dump(
                mode="json"
            ),
        }
        left_expected = {
            **left_expected,
            "source_revision": left_revision.id,
            "source_checksum": left_revision.checksum,
        }
    concept_wording = "Shared" if shared else "తెలుగు భావన"
    revision = pair_revision(
        service,
        version,
        "telugu",
        ["Telugu"],
        {"text": f"VIII Telugu Science Unit తెలుగు బలం తెలుగు విషయం {concept_wording} SRC-R1"},
    )
    specs = []
    parent = None
    for kind, title in zip(
        ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"),
        ("VIII", "Telugu", "Science", "Unit", "తెలుగు బలం", "తెలుగు విషయం", concept_wording),
        strict=True,
    ):
        code = "telugu-" + kind
        specs.append(
            CurriculumNodeSpec(
                node_type=kind,
                code=code,
                title=title,
                parent_code=parent,
                official_text=title,
                source_locator="JSON pointer /text",
                metadata_json={
                    "identity": {
                        "grade": "VIII",
                        "medium": "Telugu",
                        "subject": "Science",
                        **EXTRAS,
                    },
                    **({"official_code": "SRC-R1"} if kind == "concept" else {}),
                },
            )
        )
        parent = code
    nodes = service.upsert_nodes(version=version, revision=revision, specs=specs)
    right_observed = {
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": version.version_code,
        "synthetic": False,
        "path": service.curriculum_path(nodes["telugu-concept"].id).model_dump(mode="json"),
    }
    right_expected = {
        **left_expected,
        "key": "telugu-side",
        "source_revision": revision.id,
        "source_checksum": revision.checksum,
        "medium": "Telugu",
        "chapter": "తెలుగు బలం",
    }
    left_node = service.session.get(CurriculumNode, left_observed["path"]["node_ids"][-1])
    declaration = {
        "left_code": left_node.code,
        "right_code": "telugu-concept",
        "locator": "JSON pointer /link",
        "evidence_text": "The English node SRC-L1 corresponds to the Telugu node SRC-R1.",
    }
    evidence = pair_revision(
        service,
        version,
        "correspondence",
        ["English", "Telugu"],
        {
            "text": "This reviewed correspondence applies to VIII Science in both media.",
            "link": declaration,
        },
        [declaration],
    )
    relationship_id = link_correspondence(
        service,
        version,
        left_node_id=left_node.id,
        right_node_id=nodes["telugu-concept"].id,
        revision=evidence,
        locator=declaration["locator"],
        evidence_text=declaration["evidence_text"],
    )
    requirement = {
        "key": "scert-viii-science-telugu-correspondence",
        "materialization_type": "cross_medium_correspondence",
        "left": left_expected,
        "right": right_expected,
        "correspondence": {
            **declaration,
            "node_type": "concept",
            "source_revision": evidence.id,
            "source_checksum": evidence.checksum,
        },
    }
    observation = {
        "key": requirement["key"],
        "materialization_type": "cross_medium_correspondence",
        "synthetic": False,
        "version_id": version.id,
        "relationship_id": relationship_id,
        "left": left_observed,
        "right": right_observed,
    }
    scope["required_detailed_slices"].append(requirement)
    report["materialized_slices"].append(observation)
    service.session.commit()
    service.session.expire_all()
    return service, report, scope, version


def test_correspondence_requires_true_persisted_paired_evidence(paired):
    service, report, scope, _ = paired
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert result["passed"], result
    assert result["verified_detailed_slice_count"] == 3
    assert result["verified_materialization_counts"]["cross_medium_correspondence"] == 1


@pytest.mark.parametrize(
    "attack",
    [
        "telugu_only",
        "missing_record",
        "wrong_record",
        "same_medium",
        "missing_english",
        "other_pair",
        "wrong_version",
        "wrong_binding",
        "wrong_locator",
        "wrong_wording",
        "wrong_materialization_type",
        "unfrozen_pair",
        "corrupt_digest",
        "historical_version",
        "stale_source",
        "rehashed_wrong_pair",
    ],
)
def test_correspondence_gate_rejects_unproven_pairs(paired, attack):
    service, report, scope, version = paired
    observation = report["materialized_slices"][-1]
    required = scope["required_detailed_slices"][-1]
    if attack == "telugu_only":
        report["materialized_slices"][-1] = {**observation["right"], "key": required["key"]}
    elif attack == "missing_record":
        metadata = copy.deepcopy(version.metadata_json)
        metadata["cross_medium_correspondences"] = {}
        version.metadata_json = metadata
    elif attack == "wrong_record":
        observation["relationship_id"] = "missing"
    elif attack == "same_medium":
        observation["right"] = copy.deepcopy(observation["left"])
        required["right"] = copy.deepcopy(required["left"])
    elif attack == "missing_english":
        observation.pop("left")
    elif attack == "other_pair":
        observation["left"] = copy.deepcopy(report["materialized_slices"][1])
    elif attack == "wrong_version":
        observation["version_id"] = report["materialized_slices"][1]["path"][
            "curriculum_version_id"
        ]
    elif attack == "wrong_binding":
        required["correspondence"]["source_checksum"] = "f" * 64
    elif attack == "wrong_locator":
        required["correspondence"]["locator"] = "JSON pointer /text"
    elif attack == "wrong_wording":
        required["correspondence"]["evidence_text"] = "Unverified translation"
    elif attack == "wrong_materialization_type":
        observation["materialization_type"] = "detailed_path"
    elif attack == "unfrozen_pair":
        required["right"].pop("source_checksum")
    elif attack == "historical_version":
        version.status = "superseded"
    elif attack == "stale_source":
        evidence = service.session.get(
            SourceRevision, required["correspondence"]["source_revision"]
        )
        evidence.status = "superseded"
        evidence.active_slot = None
    elif attack == "rehashed_wrong_pair":
        metadata = copy.deepcopy(version.metadata_json)
        record = metadata["cross_medium_correspondences"].pop(observation["relationship_id"])
        record["right_id"] = report["materialized_slices"][1]["path"]["node_ids"][-1]
        new_key = hashlib.sha256(
            json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        metadata["cross_medium_correspondences"][new_key] = record
        version.metadata_json = metadata
        observation["relationship_id"] = new_key
    elif attack == "corrupt_digest":
        metadata = copy.deepcopy(version.metadata_json)
        metadata["cross_medium_correspondences"][observation["relationship_id"]][
            "evidence_text"
        ] = "corrupted"
        version.metadata_json = metadata
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert required["key"] in result["incomplete_components"]


def test_correspondence_frozen_source_bindings_replay_without_database_ids(paired, tmp_path):
    service, _, scope, _ = paired
    frozen = copy.deepcopy(scope)
    for requirement in frozen["required_detailed_slices"]:
        contracts = (
            [requirement]
            if "left" not in requirement
            else [requirement["left"], requirement["right"], requirement["correspondence"]]
        )
        for contract in contracts:
            revision = service.session.get(SourceRevision, contract.pop("source_revision"))
            contract["source_url"] = revision.metadata_json["source_snapshot"]["url"]
            contract["source_snapshot_checksum"] = revision.source_snapshot_checksum
    fresh = tmp_path / "pair-replay"
    fresh.mkdir()
    replay = globals()["persisted"].__wrapped__(fresh)
    replay_service, report, _, _ = globals()["paired"].__wrapped__(next(replay))
    try:
        result = evaluate_day5_acceptance(report, frozen, service=replay_service)
        assert result["passed"], result
        frozen["required_detailed_slices"][-1]["correspondence"]["source_snapshot_checksum"] = (
            "f" * 64
        )
        assert not evaluate_day5_acceptance(report, frozen, service=replay_service)["passed"]
    finally:
        replay.close()


RELATION_QUOTES = {
    "codes": "SRC-L1 corresponds to SRC-R1.",
    "wording": "Concept corresponds to తెలుగు భావన.",
    "internal_codes": "concept corresponds to telugu-concept.",
    "unrelated": "The annual report is ready.",
    "left_only": "SRC-L1 has been reviewed.",
    "right_only": "SRC-R1 has been reviewed.",
    "left_prefix": "SRC-L10 corresponds to SRC-R1.",
    "right_prefix": "SRC-L1 corresponds to SRC-R10.",
    "wording_prefix": "Conceptual corresponds to తెలుగు భావనాపరమైనది.",
    "cross_section": "SRC-L1 corresponds to SRC-R1.",
}


@pytest.mark.parametrize("claim", list(RELATION_QUOTES))
def test_correspondence_quote_identifies_both_endpoints_even_for_persisted_records(paired, claim):
    from app.curriculum_intelligence.scoped_curriculum import link_correspondence

    service, report, scope, version = paired
    observed = report["materialized_slices"][-1]
    required = scope["required_detailed_slices"][-1]
    original = version.metadata_json["cross_medium_correspondences"][observed["relationship_id"]]
    quote = RELATION_QUOTES[claim]
    declaration = {
        "left_code": original["left_code"],
        "right_code": original["right_code"],
        "locator": "JSON pointer /link",
        "evidence_text": quote,
    }
    content = {
        "text": "Reviewed VIII Science applicability.",
        "link": declaration,
        "outside": RELATION_QUOTES["codes"],
    }
    if claim == "cross_section":
        content["link"] = {**declaration, "evidence_text": "The annual report is ready."}
    revision = pair_revision(
        service, version, "claim-" + claim, ["English", "Telugu"], content, [declaration]
    )
    kwargs = {
        "left_node_id": original["left_id"],
        "right_node_id": original["right_id"],
        "revision": revision,
        "locator": declaration["locator"],
        "evidence_text": quote,
    }
    positive = claim in {"codes", "wording"}
    before = copy.deepcopy(version.metadata_json["cross_medium_correspondences"])
    if positive:
        relationship_id = link_correspondence(service, version, **kwargs)
    else:
        with pytest.raises(ValueError):
            link_correspondence(service, version, **kwargs)
        assert version.metadata_json["cross_medium_correspondences"] == before
        # Recreate the kind of historical/corrupt row that used to pass without endpoint proof.
        record = {
            **declaration,
            "left_id": original["left_id"],
            "right_id": original["right_id"],
            "source_revision_id": revision.id,
            "source_checksum": revision.checksum,
        }
        relationship_id = hashlib.sha256(
            json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        version.metadata_json = {
            **version.metadata_json,
            "cross_medium_correspondences": {**before, relationship_id: record},
        }
    observed["relationship_id"] = relationship_id
    required["correspondence"].update(
        **declaration, source_revision=revision.id, source_checksum=revision.checksum
    )
    service.session.flush()
    service.session.expire_all()
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert result["passed"] is positive, result
    if not positive:
        assert required["key"] in result["incomplete_components"]


SCOPE_DIMENSIONS = {
    "grade": ("grades", "IX"),
    "medium": ("media", "Telugu"),
    "subject": ("subjects", "Mathematics"),
    "course_family": ("course_families", "Vocational"),
    "course_group": ("course_groups", "MEC"),
    "subject_language": ("subject_languages", "Telugu"),
    "language_role": ("language_roles", "first"),
    "book_part": ("book_parts", "Part 2"),
    "bilingual": ("bilingual_states", "yes"),
}
ALIGNMENT_QUOTES = {
    "codes": "SRC-L1 addresses OUT-A1.",
    "wording": "Concept addresses Distinct source-backed outcome statement.",
    "internal_code": "concept addresses OUT-A1.",
    "shared_left_code": "SRC-L1 addresses Shared.",
    "shared_right_code": "Shared addresses OUT-A1.",
    "shared_only": "Shared addresses Shared.",
    "unrelated": "The annual report is ready.",
    "node_only": "SRC-L1 has been reviewed.",
    "target_only": "OUT-A1 has been reviewed.",
    "node_prefix": "SRC-L10 addresses OUT-A1.",
    "target_prefix": "SRC-L1 addresses OUT-A10.",
    "cross_section": "SRC-L1 addresses OUT-A1.",
}


def direct_alignment_case(
    persisted,
    claim="codes",
    *,
    target_dimension=None,
    cover_target=True,
    target_kind="outcome",
    target_text="Distinct source-backed outcome statement.",
):
    from app.schemas.curriculum_intelligence import (
        CompetencySpec,
        CurriculumAlignmentInput,
        LearningOutcomeSpec,
    )

    service, report, _ = persisted
    node = service.session.get(
        CurriculumNode, report["materialized_slices"][0]["path"]["node_ids"][-1]
    )
    version = node.curriculum_version
    node_identity = dict(node.metadata_json["identity"])
    target_identity = dict(node_identity)
    if target_dimension:
        target_identity[target_dimension] = SCOPE_DIMENSIONS[target_dimension][1]
    target_scope = {
        allowed: list(dict.fromkeys([node_identity[field], target_identity[field]]))
        for field, (allowed, _) in SCOPE_DIMENSIONS.items()
    }
    target_source = pair_revision(
        service,
        version,
        "alignment-target",
        target_scope["media"],
        {"text": "OUT-A1 " + target_text},
        scope_overrides=target_scope,
    )
    if target_kind == "outcome":
        target = service.upsert_learning_outcomes(
            version=version,
            revision=target_source,
            specs=[
                LearningOutcomeSpec(
                    code="alignment-target",
                    text=target_text,
                    source_locator="JSON pointer /text",
                    metadata_json={"identity": target_identity, "official_code": "OUT-A1"},
                )
            ],
        )["alignment-target"]
    else:
        target = service.upsert_competencies(
            framework=None,
            curriculum_version=version,
            revision=target_source,
            specs=[
                CompetencySpec(
                    code="alignment-target",
                    name="Scoped target",
                    official_text=target_text,
                    source_locator="JSON pointer /text",
                    metadata_json={"identity": target_identity, "official_code": "OUT-A1"},
                )
            ],
        )["alignment-target"]
    words = ALIGNMENT_QUOTES[claim]
    declaration = {
        "node_code": node.code,
        "target_id": target.id,
        "relationship_type": "addresses",
        "source_locator": "JSON pointer /link",
        "evidence_text": words,
    }
    content = {
        "text": "Reviewed mapping applicability.",
        "link": declaration,
        "outside": ALIGNMENT_QUOTES["codes"],
    }
    if claim == "cross_section":
        content["link"] = {**declaration, "evidence_text": "The annual report is ready."}
    mapping_scope = (
        target_scope
        if cover_target
        else {allowed: [node_identity[field]] for field, (allowed, _) in SCOPE_DIMENSIONS.items()}
    )
    revision = pair_revision(
        service,
        version,
        "direct-mapping",
        mapping_scope["media"],
        content,
        alignments=[declaration],
        scope_overrides=mapping_scope,
    )
    payload = CurriculumAlignmentInput(
        curriculum_version_id=version.id,
        curriculum_node_id=node.id,
        **(
            {"learning_outcome_id": target.id}
            if target_kind == "outcome"
            else {"competency_id": target.id}
        ),
        source_revision_id=revision.id,
        status="direct",
        relationship_type="addresses",
        source_locator=declaration["source_locator"],
        evidence_text=words,
    )
    return service, target, payload


@pytest.mark.parametrize(
    "claim", [claim for claim in ALIGNMENT_QUOTES if not claim.startswith("shared_")]
)
@pytest.mark.parametrize("target_kind", ["outcome", "competency"])
def test_scoped_direct_alignment_quote_must_identify_both_endpoints(persisted, claim, target_kind):
    from sqlalchemy import select

    from app.models.curriculum_intelligence import CurriculumAlignment

    service, _, payload = direct_alignment_case(persisted, claim, target_kind=target_kind)
    before = list(service.session.scalars(select(CurriculumAlignment.id)))
    if claim in {"codes", "wording"}:
        assert service.align(payload).evidence_text == ALIGNMENT_QUOTES[claim]
    else:
        with pytest.raises(ValueError):
            service.align(payload)
        assert list(service.session.scalars(select(CurriculumAlignment.id))) == before


@pytest.mark.parametrize("dimension", list(SCOPE_DIMENSIONS))
@pytest.mark.parametrize("cover_target", [False, True])
@pytest.mark.parametrize("target_kind", ["outcome", "competency"])
def test_direct_mapping_covers_target_scope_and_complete_endpoint_compatibility(
    persisted, dimension, cover_target, target_kind
):
    service, _, payload = direct_alignment_case(
        persisted, target_dimension=dimension, cover_target=cover_target, target_kind=target_kind
    )
    with pytest.raises(ValueError):
        service.align(payload)


@pytest.mark.parametrize("dimension", list(SCOPE_DIMENSIONS))
@pytest.mark.parametrize("missing", [True, False])
@pytest.mark.parametrize("target_kind", ["outcome", "competency"])
def test_direct_mapping_rejects_incomplete_target_identity(
    persisted, dimension, missing, target_kind
):
    service, target, payload = direct_alignment_case(persisted, target_kind=target_kind)
    metadata = copy.deepcopy(target.metadata_json)
    if missing:
        metadata["identity"].pop(dimension)
    else:
        metadata["identity"][dimension] = "unknown"
    target.metadata_json = metadata
    service.session.flush()
    with pytest.raises(ValueError):
        service.align(payload)


SHARED_RELATION_QUOTES = {
    "codes": "SRC-L1 corresponds to SRC-R1.",
    "left_code": "SRC-L1 corresponds to Shared.",
    "right_code": "Shared corresponds to SRC-R1.",
    "shared_only": "Shared corresponds to Shared.",
    "internal_only": "shared-left-concept corresponds to telugu-concept.",
}


@pytest.mark.parametrize("claim", list(SHARED_RELATION_QUOTES))
def test_shared_wording_requires_independent_proven_identity_for_each_correspondence_endpoint(
    persisted, claim
):
    from app.curriculum_intelligence.scoped_curriculum import link_correspondence

    service, report, scope, version = _paired_case(persisted, shared=True)
    observation = report["materialized_slices"][-1]
    required = scope["required_detailed_slices"][-1]
    old = version.metadata_json["cross_medium_correspondences"][observation["relationship_id"]]
    words = SHARED_RELATION_QUOTES[claim]
    declaration = {
        "left_code": old["left_code"],
        "right_code": old["right_code"],
        "locator": "JSON pointer /link",
        "evidence_text": words,
    }
    revision = pair_revision(
        service,
        version,
        "shared-claim-" + claim,
        ["English", "Telugu"],
        {"text": "Reviewed same-version correspondence.", "link": declaration},
        [declaration],
    )
    kwargs = {
        "left_node_id": old["left_id"],
        "right_node_id": old["right_id"],
        "revision": revision,
        "locator": declaration["locator"],
        "evidence_text": words,
    }
    if claim == "codes":
        key = link_correspondence(service, version, **kwargs)
    else:
        with pytest.raises(ValueError):
            link_correspondence(service, version, **kwargs)
        record = {
            **declaration,
            "left_id": old["left_id"],
            "right_id": old["right_id"],
            "source_revision_id": revision.id,
            "source_checksum": revision.checksum,
        }
        key = hashlib.sha256(
            json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        version.metadata_json = {
            **version.metadata_json,
            "cross_medium_correspondences": {
                **version.metadata_json["cross_medium_correspondences"],
                key: record,
            },
        }
    required["correspondence"].update(
        **declaration, source_revision=revision.id, source_checksum=revision.checksum
    )
    observation["relationship_id"] = key
    service.session.flush()
    service.session.expire_all()
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert result["passed"] is (claim == "codes"), result


@pytest.mark.parametrize("claim", ["codes", "shared_left_code", "shared_right_code", "shared_only"])
@pytest.mark.parametrize("target_kind", ["outcome", "competency"])
def test_shared_wording_plus_one_code_cannot_authorize_scoped_direct_mapping(
    persisted, claim, target_kind
):
    service, report, scope, _ = _paired_case(persisted, shared=True)
    # Select the legitimately ingested Shared node, not a tampered original endpoint.
    report["materialized_slices"][0] = copy.deepcopy(report["materialized_slices"][-1]["left"])
    service, _, payload = direct_alignment_case(
        (service, report, scope), claim, target_kind=target_kind, target_text="Shared"
    )
    if claim == "codes":
        assert service.align(payload).status == "direct"
    else:
        with pytest.raises(ValueError):
            service.align(payload)
