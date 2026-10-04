"""Build scoped catalogue snapshots from reviewed Telangana syllabus inventories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.curriculum_intelligence.scoped_catalogue import (
    CatalogueSnapshot,
    ScopedCatalogueRow,
)
from app.curriculum_intelligence.telangana_syllabus import ParsedSyllabus

if TYPE_CHECKING:
    from app.models.curriculum import CurriculumVersion
    from app.models.source import SourceRevision


def syllabus_catalogue_snapshot(
    *,
    pack_id: str,
    version_id: str,
    revision: SourceRevision,
    parsed: ParsedSyllabus,
    grade: str,
    medium: str,
    academic_year: str,
) -> CatalogueSnapshot:
    rows = [
        ScopedCatalogueRow(
            pack_id=pack_id,
            version_id=version_id,
            source_revision_id=revision.id,
            source_checksum=revision.checksum,
            source_locator=f"{parsed.subject_label} syllabus inventory",
            official_label=parsed.subject_label,
            grade=grade,
            academic_year=academic_year,
            instructional_medium=medium,
            subject_language=medium,
            resource_kind="syllabus_document",
            document_content_status="reviewed",
        )
    ]
    for chapter in parsed.chapters:
        rows.append(
            ScopedCatalogueRow(
                pack_id=pack_id,
                version_id=version_id,
                source_revision_id=revision.id,
                source_checksum=revision.checksum,
                source_locator=chapter.locator,
                official_label=f"{chapter.number}. {chapter.title}",
                grade=grade,
                academic_year=academic_year,
                instructional_medium=medium,
                subject_language=medium,
                resource_kind="syllabus_document",
                document_content_status="reviewed",
            )
        )
    return CatalogueSnapshot(
        source_revision_id=revision.id,
        source_checksum=revision.checksum,
        rows=tuple(rows),
        extraction_method="telangana-syllabus-inventory",
        inventory_status="complete",
    )


def pack_catalogue_report(
    *,
    pack_code: str,
    version: CurriculumVersion,
    snapshot: CatalogueSnapshot,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pack_code": pack_code,
        "version_id": version.id,
        "source_completeness_verified": True,
        "synthetic": False,
        "coverage": {
            "status": snapshot.inventory_status,
            "snapshot_row_count": len(snapshot.rows),
            "materialized_metadata_count": coverage.get("materialized_metadata_count", 0),
            "missing_ids": coverage.get("missing_ids", []),
            "unexpected_ids": coverage.get("unexpected_ids", []),
            "duplicate_ids": coverage.get("duplicate_ids", []),
            "conflicting_ids": coverage.get("conflicting_ids", []),
        },
    }
