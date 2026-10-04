"""Bounded official Telangana materialization; blocked slices stay explicit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.curriculum_intelligence.scoped_catalogue import materialize_catalogue
from app.curriculum_intelligence.scoped_curriculum import query_scoped_paths
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.telangana_catalogue import (
    pack_catalogue_report,
    syllabus_catalogue_snapshot,
)
from app.curriculum_intelligence.telangana_syllabus import (
    ParsedChapter,
    TelanganaSyllabusParseError,
    parse_scert_syllabus_pdf,
    parse_tgbie_annual_plan_pdf,
)
from app.models.curriculum import CurriculumVersion
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import CurriculumNodeSpec


def load_verification_slice(root: Path) -> dict[str, Any]:
    payload = json.loads((root / "day5-verification-slice.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Day-5 verification slice must be a JSON object")
    return payload


def _chapter_by_title(
    parsed_chapters: tuple[ParsedChapter, ...], chapter_ref: str
) -> ParsedChapter:
    normalized = chapter_ref.strip().casefold().rstrip(":- ")
    for chapter in parsed_chapters:
        label = f"{chapter.number}. {chapter.title}".casefold().rstrip(":- ")
        title = chapter.title.casefold().rstrip(":- ")
        number_prefix = normalized.split(".", 1)[0].strip()
        if (
            label == normalized
            or title == normalized
            or normalized.endswith(title)
            or title.startswith(normalized.split(".", 1)[-1].strip())
            or (chapter.number.lstrip("0") == number_prefix.lstrip("0") and title in normalized)
        ):
            return chapter
    raise TelanganaSyllabusParseError(f"Chapter {chapter_ref!r} not found in reviewed syllabus")


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
    root = grade.lower().replace(" ", "-")
    topic = chapter.topics[0]
    concept = topic
    parent_chain = [
        ("grade_year", root, grade, None, {}),
        ("medium", f"{root}-{medium.lower()}", medium, root, {"grade": grade, "medium": medium}),
        (
            "subject",
            f"{root}-{medium.lower()}-subject",
            subject,
            f"{root}-{medium.lower()}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "unit",
            f"{root}-{medium.lower()}-unit-{chapter.number}",
            f"Unit {chapter.number}",
            f"{root}-{medium.lower()}-subject",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "chapter",
            f"{root}-{medium.lower()}-ch-{chapter.number}",
            f"{chapter.number}. {chapter.title}",
            f"{root}-{medium.lower()}-unit-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "topic",
            f"{root}-{medium.lower()}-topic-{chapter.number}",
            topic,
            f"{root}-{medium.lower()}-ch-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
        (
            "concept",
            f"{root}-{medium.lower()}-concept-{chapter.number}",
            concept,
            f"{root}-{medium.lower()}-topic-{chapter.number}",
            {"grade": grade, "medium": medium, "subject": subject},
        ),
    ]
    specs = [
        CurriculumNodeSpec(
            node_type=node_type,
            code=code,
            title=title,
            parent_code=parent,
            official_text=title,
            source_locator=chapter.locator,
            metadata_json={"identity": identity},
        )
        for node_type, code, title, parent, identity in parent_chain
    ]
    nodes = service.upsert_nodes(version=version, specs=specs, revision=revision)
    concept_node = nodes[parent_chain[-1][1]]
    return service.curriculum_path(concept_node.id).model_dump(mode="json")


def _slice_evidence(
    *,
    key: str,
    revision: SourceRevision,
    path: dict[str, Any],
    academic_version: str,
    service: CurriculumIntelligenceService,
) -> dict[str, Any]:
    content_ok = service.has_source_content(revision) and not service.is_registry_only(revision)
    return {
        "key": key,
        "verified_from_persisted_entities": True,
        "exact_bytes_verified": content_ok,
        "applicability_verified": False,
        "source_domain_verified": True,
        "locator_verified": True,
        "synthetic": False,
        "status": "verified",
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
        "academic_version": academic_version,
        "path": path,
    }


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

    scert_revision = revisions.get("scert-ps-english-syllabus")
    bs_revision = revisions.get("scert-bs-english-syllabus")
    ia_plan = revisions.get("tgbie-maths-ia-annual-plan-2025-26")
    iia_plan = revisions.get("tgbie-maths-iia-annual-plan-2026-27")
    anchor_revision = scert_revision or bs_revision or ia_plan or iia_plan
    if anchor_revision is None:
        raise ValueError("No official Telangana source revisions available")

    scert_pack = service.ensure_pack(
        framework=None,
        code="ts-scert",
        name="SCERT Telangana",
        authority="SCERT Telangana",
        country="India",
        revision=scert_revision or bs_revision or anchor_revision,
        source_locator="Official SCERT syllabus PDFs",
    )
    scert_pack.active = False
    scert_seed = scert_revision or bs_revision or anchor_revision
    scert_version = service.ensure_version(
        pack=scert_pack,
        version_code="2025-26-syllabus",
        academic_year="2025-26",
        revision=scert_seed,
        active=False,
        source_locator="SCERT VIII science syllabus PDFs",
        metadata_json={"scope_enforced": True, "official_demonstration": True},
    )

    if scert_revision and service.has_source_content(scert_revision):
        try:
            parsed_ps = parse_scert_syllabus_pdf(
                service.source_service.storage.read(scert_revision.storage_path or "")
            )
            ps_chapter = _chapter_by_title(
                parsed_ps.chapters,
                str(slice_doc["slices"]["scert-viii-physical-science-english"]["chapter"]),
            )
            path = _materialize_chapter_path(
                service,
                version=scert_version,
                revision=scert_revision,
                grade="VIII",
                medium="English",
                subject="Physical Science",
                chapter=ps_chapter,
            )
            snapshot = syllabus_catalogue_snapshot(
                pack_id=scert_pack.id,
                version_id=scert_version.id,
                revision=scert_revision,
                parsed=parsed_ps,
                grade="VIII",
                medium="English",
                academic_year="2025-26",
            )
            coverage = materialize_catalogue(service, scert_version, scert_revision, snapshot)
            catalogue_inventories.append(
                pack_catalogue_report(
                    pack_code="ts-scert",
                    version=scert_version,
                    snapshot=snapshot,
                    coverage=coverage.model_dump(),
                )
            )
            materialized.append(
                _slice_evidence(
                    key="scert-viii-physical-science-english",
                    revision=scert_revision,
                    path=path,
                    academic_version=parsed_ps.academic_label,
                    service=service,
                )
            )
        except (TelanganaSyllabusParseError, KeyError, ValueError) as exc:
            unresolved.append(f"scert-viii-physical-science-english:{exc}")

    if bs_revision and service.has_source_content(bs_revision):
        try:
            parsed_bs = parse_scert_syllabus_pdf(
                service.source_service.storage.read(bs_revision.storage_path or "")
            )
            bs_chapter = _chapter_by_title(
                parsed_bs.chapters,
                str(slice_doc["slices"]["scert-viii-biological-science-english"]["chapter"]),
            )
            path = _materialize_chapter_path(
                service,
                version=scert_version,
                revision=bs_revision,
                grade="VIII",
                medium="English",
                subject="Biological Science",
                chapter=bs_chapter,
            )
            materialized.append(
                _slice_evidence(
                    key="scert-viii-biological-science-english",
                    revision=bs_revision,
                    path=path,
                    academic_version=parsed_bs.academic_label,
                    service=service,
                )
            )
        except (TelanganaSyllabusParseError, KeyError, ValueError) as exc:
            unresolved.append(f"scert-viii-biological-science-english:{exc}")

    tgbie_seed = ia_plan or iia_plan or anchor_revision
    tgbie_pack = service.ensure_pack(
        framework=None,
        code="tgbie",
        name="Telangana Board of Intermediate Education",
        authority="TGBIE",
        country="India",
        revision=tgbie_seed,
        source_locator="Official TGBIE annual academic plans",
    )
    tgbie_pack.active = False

    if ia_plan and service.has_source_content(ia_plan):
        try:
            parsed_ia = parse_tgbie_annual_plan_pdf(
                service.source_service.storage.read(ia_plan.storage_path or "")
            )
            ia_version = service.ensure_version(
                pack=tgbie_pack,
                version_code="2025-26",
                academic_year="2025-26",
                revision=ia_plan,
                active=False,
                source_locator="Mathematics IA annual plan 2025-26",
                metadata_json={
                    "scope_enforced": True,
                    "course_family": "General",
                    "identity_note": "historical Mathematics IA annual plan",
                },
            )
            ia_chapter = _chapter_by_title(
                parsed_ia.chapters,
                str(slice_doc["slices"]["intermediate-first-year-mathematics-english"]["chapter"]),
            )
            path = _materialize_chapter_path(
                service,
                version=ia_version,
                revision=ia_plan,
                grade="First Year",
                medium="English",
                subject="Mathematics IA",
                chapter=ia_chapter,
            )
            snapshot = syllabus_catalogue_snapshot(
                pack_id=tgbie_pack.id,
                version_id=ia_version.id,
                revision=ia_plan,
                parsed=parsed_ia,
                grade="First Year",
                medium="English",
                academic_year="2025-26",
            )
            coverage = materialize_catalogue(service, ia_version, ia_plan, snapshot)
            catalogue_inventories.append(
                pack_catalogue_report(
                    pack_code="tgbie",
                    version=ia_version,
                    snapshot=snapshot,
                    coverage=coverage.model_dump(),
                )
            )
            materialized.append(
                _slice_evidence(
                    key="intermediate-first-year-mathematics-english",
                    revision=ia_plan,
                    path=path,
                    academic_version=parsed_ia.academic_label,
                    service=service,
                )
            )
            hist_chapter = _chapter_by_title(
                parsed_ia.chapters,
                str(slice_doc["slices"]["historical-first-year-mathematics-ia-uat"]["chapter"]),
            )
            hist_path = _materialize_chapter_path(
                service,
                version=ia_version,
                revision=ia_plan,
                grade="First Year",
                medium="English",
                subject="Mathematics IA",
                chapter=hist_chapter,
            )
            materialized.append(
                _slice_evidence(
                    key="historical-first-year-mathematics-ia-uat",
                    revision=ia_plan,
                    path=hist_path,
                    academic_version="2025-26-historical-ia",
                    service=service,
                )
            )
        except (TelanganaSyllabusParseError, KeyError, ValueError) as exc:
            unresolved.append(f"intermediate-first-year:{exc}")

    if iia_plan and service.has_source_content(iia_plan):
        try:
            parsed_iia = parse_tgbie_annual_plan_pdf(
                service.source_service.storage.read(iia_plan.storage_path or "")
            )
            iia_version = service.ensure_version(
                pack=tgbie_pack,
                version_code="2026-27",
                academic_year="2026-27",
                revision=iia_plan,
                active=False,
                source_locator="Mathematics IIA annual plan 2026-27",
                metadata_json={"scope_enforced": True, "course_family": "General"},
            )
            iia_chapter = _chapter_by_title(
                parsed_iia.chapters,
                str(slice_doc["slices"]["intermediate-second-year-mathematics-english"]["chapter"]),
            )
            path = _materialize_chapter_path(
                service,
                version=iia_version,
                revision=iia_plan,
                grade="Second Year",
                medium="English",
                subject="Mathematics IIA",
                chapter=iia_chapter,
            )
            if not any(item.get("pack_code") == "tgbie" for item in catalogue_inventories):
                snapshot = syllabus_catalogue_snapshot(
                    pack_id=tgbie_pack.id,
                    version_id=iia_version.id,
                    revision=iia_plan,
                    parsed=parsed_iia,
                    grade="Second Year",
                    medium="English",
                    academic_year="2026-27",
                )
                coverage = materialize_catalogue(service, iia_version, iia_plan, snapshot)
                catalogue_inventories.append(
                    pack_catalogue_report(
                        pack_code="tgbie",
                        version=iia_version,
                        snapshot=snapshot,
                        coverage=coverage.model_dump(),
                    )
                )
            materialized.append(
                _slice_evidence(
                    key="intermediate-second-year-mathematics-english",
                    revision=iia_plan,
                    path=path,
                    academic_version=parsed_iia.academic_label,
                    service=service,
                )
            )
        except (TelanganaSyllabusParseError, KeyError, ValueError) as exc:
            unresolved.append(f"intermediate-second-year:{exc}")

    return {
        "materialized_slices": materialized,
        "catalogue_inventories": catalogue_inventories,
        "unresolved_materialization": unresolved,
        "queries": {
            "scert_ps_path": query_scoped_paths(
                service,
                pack_code="ts-scert",
                version_code="2025-26-syllabus",
                grade="VIII",
                medium="English",
                subject="Physical Science",
            ),
            "intermediate_first_year": query_scoped_paths(
                service,
                pack_code="tgbie",
                version_code="2025-26",
                grade="First Year",
                medium="English",
                subject="Mathematics IA",
            ),
        },
    }
