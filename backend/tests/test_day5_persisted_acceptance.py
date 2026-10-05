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
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


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
        content = json.dumps(
            {"text": "VIII English Science Unit Force Topic Concept section 1"}
        ).encode()
        checksum = hashlib.sha256(content).hexdigest()
        for pack_code in ("ts-scert", "tgbie"):
            row = ScopedCatalogueRow(
                pack_id="pending",
                version_id="pending",
                source_revision_id="pending",
                source_checksum=checksum,
                source_locator="section 1",
                official_label="Science",
                grade="VIII",
                academic_year="2025-26",
                instructional_medium="English",
                resource_kind="syllabus_document",
            )
            draft_snapshot = CatalogueSnapshot(
                source_revision_id="pending",
                source_checksum=checksum,
                rows=(row,),
                inventory_observations=(
                    InventoryObservation(
                        source_locator=row.source_locator,
                        status="resolved",
                        reason="reviewed inventory entry",
                        row_identity=row.identity,
                    ),
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
                        "verified_locators": ["section 1"],
                        "curriculum_scope": {
                            "pack_code": pack_code,
                            "version_codes": ["2025-26"],
                            "grades": ["VIII"],
                            "media": ["English"],
                            "subjects": ["Science"],
                            "publication_status": "final",
                            "applicability_status": "verified",
                            "applicability_locator": "section 1",
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
                source_locator="section 1",
            )
            version = service.ensure_version(
                pack=pack,
                version_code="2025-26",
                academic_year="2025-26",
                revision=revision,
                active=False,
                source_locator="section 1",
                metadata_json={"scope_enforced": True},
            )
            specs = []
            parent = None
            for node_type, title in zip(
                ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"),
                ("VIII", "English", "Science", "Unit", "Force", "Topic", "Concept"),
                strict=True,
            ):
                identity = {"grade": "VIII"}
                if node_type != "grade_year":
                    identity["medium"] = "English"
                if node_type not in {"grade_year", "medium"}:
                    identity["subject"] = "Science"
                specs.append(
                    CurriculumNodeSpec(
                        node_type=node_type,
                        code=node_type,
                        title=title,
                        parent_code=parent,
                        official_text=title,
                        source_locator="section 1",
                        metadata_json={"identity": identity},
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
                    "source_locator": "section 1",
                    "pack_code": pack_code,
                    "grade": "VIII",
                    "medium": "English",
                    "subject": "Science",
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
                rows=(row,),
                inventory_observations=(
                    InventoryObservation(
                        source_locator=row.source_locator,
                        status="resolved",
                        reason="reviewed inventory entry",
                        row_identity=row.identity,
                    ),
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
    scope["packs"] = [{"code": "ts-scert", "grades": ["VIII", "IX"]}]
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue_scope" in result["incomplete_components"]


def draft_inventory(service, report, *, binding_year="2025-26"):
    """Approve a distinct draft inventory without changing its final governing source."""
    inventory = report["catalogue_inventories"][0]
    version = service.session.get(CurriculumVersion, inventory["version_id"])
    governing = service.session.get(SourceRevision, version.source_revision_id)
    original = CatalogueSnapshot.model_validate(
        version.metadata_json["scoped_catalogue_snapshots"][governing.id]["snapshot"]
    )
    metadata = copy.deepcopy(service._source_metadata(governing))
    metadata["inventory_scope"] = metadata.pop("curriculum_scope")
    metadata["inventory_scope"]["publication_status"] = "draft"
    metadata["document_type"] = "textbook_index"
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
        content=service.source_service.storage.read(governing.storage_path),
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
    if attack == "draft_alone":
        version.source_revision_id = revision.id
    result = evaluate_day5_acceptance(report, scope, service=service)
    assert not result["passed"]
    assert "ts-scert_catalogue" in result["incomplete_components"]
