"""Bounded official Telangana materialization; blocked slices stay explicit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.curriculum_intelligence.scoped_curriculum import exact_scope, validate_version_scope
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.source_domains import source_domain
from app.curriculum_intelligence.telangana_syllabus import (
    ParsedChapter,
    TelanganaSyllabusParseError,
    parse_scert_syllabus_pdf,
    parse_tgbie_annual_plan_pdf,
)
from app.models.curriculum import CurriculumPack, CurriculumVersion
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import CurriculumNodeSpec


def _usable_source(service: CurriculumIntelligenceService, revision: SourceRevision | None) -> bool:
    return bool(
        revision is not None
        and service.has_source_content(revision)
        and not service.is_registry_only(revision)
    )


def load_verification_slice(root: Path) -> dict[str, Any]:
    payload = json.loads((root / "day5-verification-slice.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Day-5 verification slice must be a JSON object")
    return payload


def _chapter_by_title(
    parsed_chapters: tuple[ParsedChapter, ...], chapter_ref: str
) -> ParsedChapter:
    normalized = chapter_ref.strip().casefold().rstrip(":- ")
    matches = [
        chapter
        for chapter in parsed_chapters
        if normalized
        in {
            f"{chapter.number}. {chapter.title}".casefold().rstrip(":- "),
            chapter.title.casefold().rstrip(":- "),
        }
    ]
    if len(matches) != 1:
        raise TelanganaSyllabusParseError(f"Chapter {chapter_ref!r} missing or ambiguous")
    return matches[0]


def _materialize_chapter_path(
    service: CurriculumIntelligenceService,
    *,
    version: CurriculumVersion,
    revision: SourceRevision,
    grade: str,
    medium: str,
    subject: str,
    chapter: ParsedChapter,
) -> dict[str, Any]:
    # Each immutable source-bound hierarchy owns its ancestors too: sharing a
    # grade node across documents would overwrite its exact-source locator.
    subject_key = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]
    root = f"{grade.lower().replace(' ', '-')}-{medium.lower()}-{subject_key}"
    if not chapter.topics or not chapter.topic_locators:
        raise TelanganaSyllabusParseError(
            "Exact topic text and locator required for a detailed path"
        )
    branch = f"{root}-{medium.lower()}"
    topic = chapter.topics[0]
    concept = topic
    parent_chain = [
        ("grade_year", root, grade, None, {"grade": grade}),
        ("medium", f"{root}-{medium.lower()}", medium, root, {"grade": grade, "medium": medium}),
        (
            "subject",
            f"{branch}-subject",
            subject,
            f"{root}-{medium.lower()}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "unit",
            f"{branch}-unit-{chapter.number}",
            f"Unit {chapter.number}",
            f"{branch}-subject",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "chapter",
            f"{branch}-ch-{chapter.number}",
            f"{chapter.number}. {chapter.title}",
            f"{branch}-unit-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "topic",
            f"{branch}-topic-{chapter.number}",
            topic,
            f"{branch}-ch-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "concept",
            f"{branch}-concept-{chapter.number}",
            concept,
            f"{branch}-topic-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
    ]
    specs = [
        CurriculumNodeSpec(
            node_type=node_type,
            code=code,
            title=title,
            parent_code=parent,
            official_text=(
                chapter.title if node_type == "chapter" else topic if node_type == "topic" else None
            ),
            source_locator=(
                chapter.topic_locators[0] if node_type in {"topic", "concept"} else chapter.locator
            ),
            metadata_json={
                "identity": identity,
                "label_status": ("official" if node_type in {"chapter", "topic"} else "derived"),
            },
        )
        for node_type, code, title, parent, identity in parent_chain
    ]
    nodes = service.upsert_nodes(version=version, specs=specs, revision=revision)
    concept_node = nodes[parent_chain[-1][1]]
    return service.curriculum_path(concept_node.id).model_dump(mode="json")


def materialize_reviewed_slice(
    service: CurriculumIntelligenceService,
    *,
    version: CurriculumVersion,
    revision: SourceRevision,
    frozen: dict[str, Any],
) -> dict[str, Any]:
    """Materialize only a frozen, reviewed governing source into an existing version.

    The frozen record is the checked-in scope contract, never a report payload.
    Exact source metadata and review fingerprint are independently revalidated.
    """
    chapter = _reviewed_chapter(service, revision, frozen)
    validate_version_scope(
        service,
        revision,
        pack_code=version.curriculum_pack.code,
        version_code=version.version_code,
        active=True,
    )
    if (
        version.version_code != frozen["academic_version"]
        or version.curriculum_pack.code != frozen["pack_code"]
        or not version.metadata_json.get("scope_enforced")
    ):
        raise TelanganaSyllabusParseError("Persisted version does not match frozen scope")
    path = _materialize_chapter_path(
        service,
        version=version,
        revision=revision,
        grade=frozen["grade"],
        medium=frozen["medium"],
        subject=frozen["subject"],
        chapter=chapter,
    )
    return {
        "key": frozen["key"],
        "status": "materialized_pending_verification",
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": version.version_code,
        "synthetic": False,
        "path": path,
    }


def _reviewed_chapter(
    service: CurriculumIntelligenceService, revision: SourceRevision, frozen: dict[str, Any]
) -> ParsedChapter:
    fields = (
        "key",
        "chapter",
        "academic_version",
        "source_checksum",
        "source_locator",
        "topic_locator",
        "pack_code",
        "grade",
        "medium",
        "subject",
    )
    if not all(frozen.get(field) for field in fields):
        raise TelanganaSyllabusParseError("Incomplete frozen source contract")
    snapshot = revision.metadata_json.get("source_snapshot", {})
    if source_domain(snapshot) != "syllabus":
        raise TelanganaSyllabusParseError(
            "Governing syllabus required; supporting source cannot establish membership"
        )
    scope = exact_scope(service, revision)
    metadata = service._source_metadata(revision)
    if (
        metadata.get("synthetic") is not False
        or scope.publication_status != "final"
        or scope.applicability_status != "verified"
    ):
        raise TelanganaSyllabusParseError("Final reviewed official applicability required")
    if (
        scope.pack_code != frozen["pack_code"]
        or frozen["academic_version"] not in scope.version_codes
        or frozen["grade"] not in scope.grades
        or frozen["medium"] not in scope.media
        or frozen["subject"] not in scope.subjects
    ):
        raise TelanganaSyllabusParseError("Frozen identity is outside reviewed source scope")
    if frozen.get("source_revision"):
        if revision.id != frozen["source_revision"]:
            raise TelanganaSyllabusParseError("Frozen revision mismatch")
    elif not (frozen.get("source_url") and frozen.get("source_snapshot_checksum")):
        raise TelanganaSyllabusParseError("Frozen revision or immutable source identity required")
    if (
        revision.checksum != frozen["source_checksum"]
        or (frozen.get("source_url") and snapshot.get("url") != frozen["source_url"])
        or (
            frozen.get("source_snapshot_checksum")
            and revision.source_snapshot_checksum != frozen["source_snapshot_checksum"]
        )
    ):
        raise TelanganaSyllabusParseError("Frozen source checksum or URL mismatch")
    reviewed_locators = metadata.get("verified_locators", [])
    for locator in (scope.applicability_locator, frozen["source_locator"], frozen["topic_locator"]):
        if not locator or (
            locator not in reviewed_locators and locator not in (revision.extracted_text or "")
        ):
            raise TelanganaSyllabusParseError("Exact source locator has not been reviewed")
    content = service.source_service.storage.read(revision.storage_path or "")
    parsed = (
        parse_scert_syllabus_pdf(content, grade=frozen["grade"])
        if frozen["pack_code"] == "ts-scert"
        else parse_tgbie_annual_plan_pdf(content)
    )
    if parsed.grade_label != frozen["grade"] or parsed.subject_label != frozen["subject"]:
        raise TelanganaSyllabusParseError("Parsed document identity differs from frozen scope")
    chapter = _chapter_by_title(parsed.chapters, frozen["chapter"])
    if (
        frozen["chapter"] != f"{chapter.number}. {chapter.title}"
        or chapter.locator != frozen["source_locator"]
        or not chapter.topics
        or chapter.topic_locators[0] != frozen["topic_locator"]
    ):
        raise TelanganaSyllabusParseError("Frozen chapter or topic differs from exact extraction")
    return chapter


def _ensure_frozen_version(
    service: CurriculumIntelligenceService, revision: SourceRevision, frozen: dict[str, Any]
) -> CurriculumVersion:
    """Create only explicitly frozen identity; reuse immutable matching versions."""
    if not all(
        frozen.get(field)
        for field in (
            "pack_name",
            "pack_code",
            "academic_version",
            "academic_year",
        )
    ):
        raise TelanganaSyllabusParseError("Frozen pack name and academic identity required")
    snapshot = revision.metadata_json["source_snapshot"]
    if not snapshot.get("authority") or not snapshot.get("country"):
        raise TelanganaSyllabusParseError("Reviewed source authority and country required")
    if snapshot.get("academic_year") != frozen["academic_year"]:
        raise TelanganaSyllabusParseError("Frozen academic year differs from reviewed source")
    pack = service.session.scalar(
        select(CurriculumPack).where(
            CurriculumPack.code == frozen["pack_code"],
        )
    )
    if pack is None:
        pack = service.ensure_pack(
            framework=None,
            code=frozen["pack_code"],
            name=frozen["pack_name"],
            authority=snapshot["authority"],
            country=snapshot["country"],
            revision=revision,
            source_locator=frozen["source_locator"],
            metadata_json={"scope_enforced": True},
        )
        pack.active = False
    elif (
        pack.name != frozen["pack_name"]
        or pack.authority != snapshot["authority"]
        or pack.country != snapshot["country"]
        or pack.framework_id is not None
        or not pack.metadata_json.get("scope_enforced")
    ):
        raise TelanganaSyllabusParseError("Existing pack differs from frozen identity")
    version = service.session.scalar(
        select(CurriculumVersion).where(
            CurriculumVersion.curriculum_pack_id == pack.id,
            CurriculumVersion.version_code == frozen["academic_version"],
        )
    )
    if version is None:
        version = service.ensure_version(
            pack=pack,
            version_code=frozen["academic_version"],
            academic_year=frozen["academic_year"],
            revision=revision,
            source_locator=frozen["source_locator"],
            active=False,
            metadata_json={"scope_enforced": True},
        )
    elif version.academic_year != frozen["academic_year"]:
        raise TelanganaSyllabusParseError("Existing version differs from frozen academic year")
    return version


def official_telangana_demonstration(
    service: CurriculumIntelligenceService,
    revisions: dict[str, SourceRevision],
    *,
    content_root: Path,
) -> dict[str, Any]:
    slice_doc = load_verification_slice(content_root)
    materialized: list[dict[str, Any]] = []
    catalogue_inventories: list[dict[str, Any]] = []
    unresolved: list[str] = []
    extracted: list[dict[str, Any]] = []

    handled: set[str] = set()
    for key, record in slice_doc.get("slices", {}).items():
        if not isinstance(record, dict) or not (
            record.get("curriculum_version_id") or record.get("source_checksum")
        ):
            continue
        handled.add(key)
        try:
            revision = revisions.get(str(record.get("source_manifest_key")))
            if revision is None:
                raise TelanganaSyllabusParseError("Frozen source revision is unavailable")
            frozen = {**record, "key": key}
            # All preflight checks and writes share a savepoint. An invalid
            # chapter, scope or source leaves no orphaned pack/version/nodes.
            with service.session.begin_nested():
                _reviewed_chapter(service, revision, frozen)
                if record.get("curriculum_version_id"):
                    version = service.session.get(
                        CurriculumVersion, record["curriculum_version_id"]
                    )
                    if version is None:
                        raise TelanganaSyllabusParseError("Reviewed persisted version is missing")
                else:
                    version = _ensure_frozen_version(service, revision, frozen)
                evidence = materialize_reviewed_slice(
                    service,
                    version=version,
                    revision=revision,
                    frozen=frozen,
                )
            materialized.append(evidence)
        except (ValueError, KeyError, OSError) as exc:
            unresolved.append(f"{key}:{exc}")

    scert_revision = revisions.get("scert-ps-english-syllabus")
    bs_revision = revisions.get("scert-bs-english-syllabus")
    scert_catalogue = revisions.get("scert-textbooks-catalogue-2025-26")
    for key, revision, expected_subject in (
        ("scert-viii-physical-science-english", scert_revision, "Physical Science"),
        ("scert-viii-biological-science-english", bs_revision, "Biological Science"),
    ):
        if key in handled:
            continue
        if not _usable_source(service, revision) or revision is None:
            unresolved.append(f"{key}:official_bytes_unavailable")
            continue
        try:
            content = service.source_service.storage.read(revision.storage_path or "")
            if hashlib.sha256(content).hexdigest() != revision.checksum:
                raise TelanganaSyllabusParseError("Stored bytes do not match source checksum")
            parsed = parse_scert_syllabus_pdf(content, grade="VIII")
            if parsed.subject_label != expected_subject:
                raise TelanganaSyllabusParseError("Source subject does not match requested slice")
            chapter = _chapter_by_title(parsed.chapters, str(slice_doc["slices"][key]["chapter"]))
            extracted.append(
                {
                    "key": key,
                    "status": "extracted_only",
                    "source_revision_id": revision.id,
                    "source_checksum": revision.checksum,
                    "grade": parsed.grade_label,
                    "subject": parsed.subject_label,
                    "academic_year_label": parsed.academic_year,
                    "chapter": chapter.title,
                    "locator": chapter.locator,
                    "topic_count": len(chapter.topics),
                }
            )
            # Extracted headings do not independently establish medium or academic
            # applicability. Registry labels are not proof of either dimension.
            unresolved.append(f"{key}:persisted_applicability_and_medium_evidence_required")
        except (TelanganaSyllabusParseError, KeyError, ValueError, OSError) as exc:
            unresolved.append(f"{key}:{exc}")
    if scert_catalogue is not None:
        unresolved.append("scert-textbook-catalogue:governing_version_applicability_required")

    if not any(item["key"].startswith("intermediate-") for item in materialized):
        unresolved.append(
            "tgbie-pack:governing_syllabus_required;annual_plans_are_supporting_calendar_evidence"
        )
    return {
        "extracted_slices": extracted,
        "materialized_slices": materialized,
        "catalogue_inventories": catalogue_inventories,
        "unresolved_materialization": unresolved,
        "queries": {},
    }
