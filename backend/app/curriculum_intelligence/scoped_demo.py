"""Synthetic second-pack proof. No source text or official membership is asserted."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum_intelligence.scoped_catalogue import (
    CatalogueSnapshot,
    CourseApplicability,
    ScopedCatalogueRow,
    materialize_catalogue,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.curriculum import CurriculumVersion
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.models.source import Source, SourceRevision
from app.schemas.curriculum_intelligence import (
    CompetencySpec,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    LearningOutcomeSpec,
)
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def synthetic_revision(
    service: CurriculumIntelligenceService,
    *,
    pack: str,
    domain: str,
    version_code: str = "synthetic-2025-26",
    grades: tuple[str, ...] = ("VIII",),
    media: tuple[str, ...] = ("English", "Telugu"),
    subjects: tuple[str, ...] = ("science",),
) -> SourceRevision:
    url = f"https://synthetic.example.invalid/{pack}/{version_code}/{domain}.json"
    source = service.session.scalar(select(Source).where(Source.url == url))
    if source is None:
        source = service.source_service.register_source(
            SourceRegistrationInput(
                source_type=SourceType.OFFICIAL_SYLLABUS
                if domain == "syllabus"
                else SourceType.OFFICIAL_AUTHORITY,
                title=f"SYNTHETIC {pack} {domain}; not official content",
                url=url,
                authority="Synthetic test authority",
                country="India",
                board_or_exam=pack,
                academic_year=version_code,
                copyright_classification="synthetic_fixture",
                trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                metadata_json={
                    "document_type": domain,
                    "synthetic": True,
                    "curriculum_scope": {
                        "pack_code": pack,
                        "version_codes": [version_code],
                        "grades": grades,
                        "media": media,
                        "subjects": subjects,
                        "course_families": ["not_applicable"],
                        "course_groups": ["not_applicable"],
                        "subject_languages": ["not_applicable"],
                        "language_roles": ["not_applicable"],
                        "book_parts": ["not_applicable"],
                        "bilingual_states": ["not_applicable", "no"],
                        "publication_status": "draft",
                        "applicability_status": "unverified",
                        "applicability_locator": "JSON pointer /subjects",
                    },
                },
            ),
            actor_id="synthetic-verifier",
        )
    revision = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="synthetic.json",
        content=json.dumps(
            {
                "fixture": True,
                "domain": domain,
                "text": (
                    "English science తెలుగు اردو हिन्दी synthetic evidence తెలుగు اردو outcome "
                    "తెలుగు ప్రమాణం Unit Chapter Topic Concept"
                ),
                "grades": grades,
                "media": media,
                "subjects": subjects,
                "catalogue": [
                    {
                        "pack_code": pack,
                        "version_code": version_code,
                        "official_label": "తెలుగు" if medium == "Telugu" else "Science",
                        "grade": grade,
                        "academic_year": "2025-26",
                        "instructional_medium": medium,
                        "subject": subject,
                        "resource_kind": "syllabus_document",
                        "course_family": "not_applicable",
                        "subject_language": "not_applicable",
                        "language_role": "not_applicable",
                        "book_part": "not_applicable",
                        "bilingual": "no",
                        "applicability": {
                            "status": "explicit_groups",
                            "groups": ["not_applicable"],
                        },
                        "not_applicable_justifications": {
                            field: "Synthetic fixture explicitly has no subdivision on this axis"
                            for field in (
                                "course_family",
                                "course_group",
                                "subject_language",
                                "language_role",
                                "book_part",
                            )
                        },
                    }
                    for grade in grades
                    for medium in media
                    for subject in subjects
                ],
            },
            ensure_ascii=False,
        ).encode(),
        actor_id="synthetic-verifier",
    )
    if revision.status == "active":
        return revision
    revision = service.source_service.extract_revision(revision.id, actor_id="synthetic-verifier")
    service.source_service.create_diff(revision.id, actor_id="synthetic-verifier")
    result = service.source_service.validate_revision(revision.id, actor_id="synthetic-verifier")
    if not result.valid:
        raise ValueError(result.errors)
    service.source_service.approve_revision(revision.id, actor_id="synthetic-verifier")
    return service.source_service.activate_revision(revision.id, actor_id="synthetic-verifier")


def seed_scoped_pack(
    service: CurriculumIntelligenceService,
    *,
    pack_code: str,
    grades: tuple[str, ...],
) -> dict[str, Any]:
    revision = synthetic_revision(service, pack=pack_code, domain="syllabus", grades=grades)
    pack = service.ensure_pack(
        framework=None,
        code=pack_code,
        name=f"SYNTHETIC {pack_code}",
        authority="Synthetic test authority",
        country="India",
        revision=revision,
        source_locator="synthetic JSON fixture",
    )
    pack.active = False
    version = service.ensure_version(
        pack=pack,
        version_code="synthetic-2025-26",
        academic_year="2025-26",
        revision=revision,
        active=False,
        source_locator="synthetic JSON fixture",
        metadata_json={"scope_enforced": True, "synthetic": True},
    )
    paths = []
    rows: list[ScopedCatalogueRow] = []
    for grade in grades:
        root = grade.lower().replace(" ", "-")
        for medium in ("English", "Telugu"):
            parent = f"{root}-{medium.lower()}-grade"
            identity: dict[str, str] = {
                "grade": grade,
                "medium": medium,
                "subject": "science",
                **dict.fromkeys(
                    (
                        "course_family",
                        "course_group",
                        "subject_language",
                        "language_role",
                        "book_part",
                        "bilingual",
                    ),
                    "not_applicable",
                ),
            }
            service.upsert_nodes(
                version=version,
                revision=revision,
                specs=[
                    CurriculumNodeSpec(
                        node_type="grade_year",
                        code=parent,
                        title=grade,
                        metadata_json={"identity": dict(identity)},
                        source_locator="JSON pointer /text",
                    )
                ],
            )
            specs = []
            for kind, label in (
                ("medium", medium),
                ("subject", "science"),
                ("unit", "Unit"),
                ("chapter", "Chapter"),
                ("topic", "Topic"),
                ("concept", "Concept"),
            ):
                if kind == "subject":
                    identity["subject"] = "science"
                code = f"{root}-{medium.lower()}-{kind}"
                specs.append(
                    CurriculumNodeSpec(
                        node_type=kind,
                        code=code,
                        title=label,
                        parent_code=parent,
                        official_text="తెలుగు" if medium == "Telugu" else label,
                        source_locator="JSON pointer /text",
                        metadata_json={"identity": dict(identity)},
                    )
                )
                parent = code
            nodes = service.upsert_nodes(version=version, specs=specs, revision=revision)
            paths.append(service.curriculum_path(nodes[parent].id).model_dump(mode="json"))
            rows.append(
                ScopedCatalogueRow(
                    pack_id=pack.id,
                    version_id=version.id,
                    source_revision_id=revision.id,
                    source_checksum=revision.checksum,
                    source_locator=f"JSON pointer /catalogue/{len(rows)}",
                    official_label="తెలుగు" if medium == "Telugu" else "Science",
                    grade=grade,
                    academic_year="2025-26",
                    instructional_medium=medium,
                    resource_kind="syllabus_document",
                    subject="science",
                    course_family="not_applicable",
                    subject_language="not_applicable",
                    language_role="not_applicable",
                    book_part="not_applicable",
                    bilingual="no",
                    applicability=CourseApplicability(
                        status="explicit_groups",
                        groups=("not_applicable",),
                        source_locator=f"JSON pointer /catalogue/{len(rows)}/applicability",
                    ),
                )
            )
    coverage = materialize_catalogue(
        service,
        version,
        revision,
        CatalogueSnapshot(
            source_revision_id=revision.id,
            source_checksum=revision.checksum,
            rows=tuple(rows),
            extraction_method="synthetic-construction",
            inventory_status="complete",
        ),
    )
    outcome_revision = synthetic_revision(
        service, pack=pack_code, domain="learning_outcomes", grades=grades
    )
    standards_revision = synthetic_revision(
        service, pack=pack_code, domain="academic_standard", grades=grades
    )
    binding_metadata = {"identity": {"grade": grades[0], "medium": "English", "subject": "science"}}
    outcome = service.upsert_learning_outcomes(
        version=version,
        revision=outcome_revision,
        specs=[
            LearningOutcomeSpec(
                code="synthetic-lo",
                text="తెలుగు اردو outcome",
                source_locator="JSON pointer /text",
                metadata_json=binding_metadata,
            )
        ],
    )["synthetic-lo"]
    competency_code = pack_code + "-standard"
    competency = service.upsert_competencies(
        framework=None,
        curriculum_version=version,
        revision=standards_revision,
        specs=[
            CompetencySpec(
                code=competency_code,
                name="Synthetic academic standard",
                official_text="తెలుగు ప్రమాణం",
                source_locator="JSON pointer /text",
                metadata_json=binding_metadata,
            )
        ],
    )[competency_code]
    outcome.active = competency.active = False
    for target, record, evidence in (
        ("learning_outcome_id", outcome, outcome_revision),
        ("competency_id", competency, standards_revision),
    ):
        service.align(
            CurriculumAlignmentInput.model_validate(
                {
                    "curriculum_version_id": version.id,
                    "curriculum_node_id": paths[0]["node_ids"][-1],
                    target: record.id,
                    "source_revision_id": evidence.id,
                    "relationship_type": "addresses",
                    "status": "partial",
                    "inferred": True,
                    "source_locator": "JSON pointer /text",
                }
            )
        )
    paths = [
        service.curriculum_path(path["node_ids"][-1]).model_dump(mode="json") for path in paths
    ]
    return {
        "pack_id": pack.id,
        "version_id": version.id,
        "paths": paths,
        "catalogue": coverage.model_dump(),
        "source_revision_id": revision.id,
        "framework_id": None,
        "status": version.status,
    }


def seed_day5_verification(session: Session, storage_root: Path) -> dict[str, Any]:
    service = CurriculumIntelligenceService(
        session,
        source_service=SourceIntelligenceService(
            session,
            storage=LocalSourceStorage(storage_root),
        ),
    )
    packs = [
        seed_scoped_pack(service, pack_code=code, grades=grades)
        for code, grades in (
            (
                "synthetic-school-pack",
                ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"),
            ),
            ("synthetic-intermediate-pack", ("First Year", "Second Year")),
        )
    ]
    session.commit()
    for result in packs:
        persisted = session.get(CurriculumVersion, result["version_id"])
        assert persisted is not None and persisted.status == "draft"
    return {
        "status": "synthetic_verification_passed",
        "official_source_backed_acceptance": False,
        "packs": packs,
        "scope": "Synthetic generic contracts only; official ingestion is blocked",
    }
