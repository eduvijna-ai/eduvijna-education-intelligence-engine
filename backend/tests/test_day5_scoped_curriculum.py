"""Adversarial generic scope contracts using real synthetic source lifecycles."""

from __future__ import annotations

import copy
import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.scoped_curriculum import link_correspondence, query_scoped_paths
from app.curriculum_intelligence.scoped_demo import (
    seed_day5_verification,
    seed_scoped_pack,
    synthetic_revision,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.curriculum import (
    Competency,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    LearningOutcome,
)
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import (
    CompetencySpec,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    LearningOutcomeSpec,
)
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


@pytest.fixture
def service(tmp_path: Path) -> Generator[CurriculumIntelligenceService, None, None]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield CurriculumIntelligenceService(
            session,
            source_service=SourceIntelligenceService(
                session, storage=LocalSourceStorage(tmp_path / "sources")
            ),
        )
    engine.dispose()


def scoped(
    service: CurriculumIntelligenceService, pack: str = "synthetic-scope"
) -> tuple[CurriculumVersion, SourceRevision]:
    result = seed_scoped_pack(service, pack_code=pack, grades=("First Year", "Second Year"))
    version = service.session.get(CurriculumVersion, result["version_id"])
    revision = service.session.get(SourceRevision, result["source_revision_id"])
    assert version is not None and revision is not None
    return version, revision


def grade(
    code: str = "new-grade", title: str = "First Year", identity: str = "First Year"
) -> CurriculumNodeSpec:
    return CurriculumNodeSpec(
        node_type="grade_year",
        code=code,
        title=title,
        source_locator="JSON pointer /text",
        metadata_json={
            "identity": {
                "grade": identity,
                "medium": "English",
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
        },
    )


def identity() -> dict[str, dict[str, str]]:
    return {
        "identity": {
            "grade": "First Year",
            "medium": "English",
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
    }


def approved_revision(
    service: CurriculumIntelligenceService,
    *,
    publication: str = "draft",
    applicability: str = "unverified",
    pack: str = "synthetic-active",
    version_code: str = "synthetic-2025-26",
    grades: tuple[str, ...] = ("First Year",),
    media: tuple[str, ...] = ("English",),
    subjects: tuple[str, ...] = ("science",),
    declarations: list[dict[str, str]] | None = None,
    alignments: list[dict[str, str]] | None = None,
    content: dict[str, Any] | None = None,
    non_applicable_dimensions: bool = False,
) -> SourceRevision:
    """Review immutable scope as registered; never fabricate SourceRevision objects."""
    source = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="SYNTHETIC governing evidence",
            url=f"https://synthetic.example.invalid/adversarial/{pack}/{publication}/{applicability}.json",
            authority="Synthetic authority",
            country="India",
            board_or_exam=pack,
            academic_year=version_code,
            copyright_classification="synthetic_fixture",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "synthetic": True,
                "correspondences": declarations or [],
                "direct_alignments": alignments or [],
                "document_type": "syllabus",
                "curriculum_scope": {
                    "pack_code": pack,
                    "version_codes": [version_code],
                    "grades": grades,
                    "media": media,
                    "subjects": subjects,
                    **(
                        {
                            key: ["not_applicable"]
                            for key in (
                                "course_families",
                                "course_groups",
                                "subject_languages",
                                "language_roles",
                                "book_parts",
                                "bilingual_states",
                            )
                        }
                        if non_applicable_dimensions
                        else {}
                    ),
                    "publication_status": publication,
                    "applicability_status": applicability,
                    "applicability_locator": "JSON pointer /text"
                    if applicability == "verified"
                    else None,
                },
            },
        ),
        actor_id="test",
    )
    revision = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="scope.json",
        content=json.dumps(
            content or {"fixture": True, "text": "తెలుగు اردو हिन्दी source evidence"}
        ).encode(),
        actor_id="test",
    )
    service.source_service.extract_revision(revision.id, actor_id="test")
    service.source_service.create_diff(revision.id, actor_id="test")
    assert service.source_service.validate_revision(revision.id, actor_id="test").valid
    service.source_service.approve_revision(revision.id, actor_id="test")
    return service.source_service.activate_revision(revision.id, actor_id="test")


def test_second_pack_demonstration_is_draft_idempotent_and_roundtrips(
    service: CurriculumIntelligenceService, tmp_path: Path
) -> None:
    first = seed_day5_verification(service.session, tmp_path / "sources")
    ids_before = set(service.session.scalars(select(CurriculumNode.id)))
    second = seed_day5_verification(service.session, tmp_path / "sources")
    assert first == second
    assert first["official_source_backed_acceptance"] is False
    assert set(service.session.scalars(select(CurriculumNode.id))) == ids_before
    service.session.expunge_all()
    packs = list(service.session.scalars(select(CurriculumPack)))
    assert len(packs) == 2
    assert all(p.framework_id is None and not p.active for p in packs)
    for result, expected_grades in zip(first["packs"], [10, 2], strict=True):
        version = service.session.get(CurriculumVersion, result["version_id"])
        assert version is not None and version.status == "draft"
        nodes = list(
            service.session.scalars(
                select(CurriculumNode).where(CurriculumNode.curriculum_version_id == version.id)
            )
        )
        assert len([n for n in nodes if n.node_type == "grade_year"]) == expected_grades * 2
        assert len(result["paths"]) == expected_grades * 2
        assert {
            n.metadata_json["identity"]["medium"] for n in nodes if n.node_type == "medium"
        } == {"English", "Telugu"}
        assert any(n.official_text == "తెలుగు" for n in nodes)
    assert all(
        not outcome.active and outcome.text == "తెలుగు اردو outcome"
        for outcome in service.session.scalars(select(LearningOutcome))
    )
    assert all(
        not standard.active and standard.framework_id is None
        for standard in service.session.scalars(select(Competency))
    )


@pytest.mark.parametrize(
    "dimension,override",
    [
        ("pack", {"pack": "synthetic-other"}),
        ("version", {"version_code": "synthetic-2026-27"}),
        ("grade", {"grades": ("VIII",)}),
        ("medium", {"media": ("Telugu",)}),
        ("subject", {"subjects": ("mathematics",)}),
    ],
)
def test_new_nodes_reject_source_from_wrong_exact_scope(
    service: CurriculumIntelligenceService, dimension: str, override: dict[str, Any]
) -> None:
    version, _ = scoped(service)
    # Distinct source URL even where only one dimension differs.
    kwargs: dict[str, Any] = {
        "pack": version.curriculum_pack.code,
        "media": ("English", "Telugu"),
        "grades": ("First Year", "Second Year"),
        **override,
    }
    revision = approved_revision(service, **kwargs)
    spec = CurriculumNodeSpec(
        node_type="unit",
        code=f"wrong-{dimension}",
        title="Synthetic unit",
        parent_code="first-year-english-subject",
        metadata_json=identity(),
        source_locator="JSON pointer /text",
    )
    with pytest.raises(ValueError, match="scope|pack|version"):
        service.upsert_nodes(version=version, revision=revision, specs=[spec])
    assert (
        service.session.scalar(select(CurriculumNode).where(CurriculumNode.code == spec.code))
        is None
    )


@pytest.mark.parametrize(
    "publication,applicability",
    [("draft", "verified"), ("final", "unverified"), ("draft", "unverified")],
)
def test_draft_or_unverified_evidence_cannot_activate_curriculum(
    service: CurriculumIntelligenceService, publication: str, applicability: str
) -> None:
    revision = approved_revision(service, publication=publication, applicability=applicability)
    pack = service.ensure_pack(
        framework=None,
        code="synthetic-active",
        name="Synthetic",
        authority="Synthetic",
        country="India",
        revision=revision,
    )
    with pytest.raises(ValueError, match="Draft|unverified"):
        service.ensure_version(
            pack=pack,
            version_code="synthetic-2025-26",
            academic_year="2025-26",
            revision=revision,
            metadata_json={"scope_enforced": True},
            active=True,
        )


@pytest.mark.parametrize("field,value", [("grade", "Second Year"), ("medium", "Telugu")])
def test_parent_scope_cannot_cross_year_or_medium(
    service: CurriculumIntelligenceService, field: str, value: str
) -> None:
    version, revision = scoped(service)
    metadata = identity()
    metadata["identity"][field] = value
    with pytest.raises(ValueError, match="parent"):
        service.upsert_nodes(
            version=version,
            revision=revision,
            specs=[
                CurriculumNodeSpec(
                    node_type="unit",
                    code="cross-parent",
                    title="Synthetic",
                    parent_code="first-year-english-subject",
                    source_locator="JSON pointer /text",
                    metadata_json=metadata,
                )
            ],
        )


def test_textbook_never_establishes_membership(service: CurriculumIntelligenceService) -> None:
    version, _ = scoped(service)
    textbook = synthetic_revision(
        service, pack=version.curriculum_pack.code, domain="textbook", grades=("First Year",)
    )
    with pytest.raises(ValueError):
        service.upsert_nodes(version=version, revision=textbook, specs=[grade()])


def test_superseded_source_rejects_new_writes_but_preserves_historical_path(
    service: CurriculumIntelligenceService,
) -> None:
    version, revision = scoped(service)
    node = service.session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id,
            CurriculumNode.code == "first-year-english-concept",
        )
    )
    assert node is not None
    old_path = service.curriculum_path(node.id)
    candidate = service.source_service.ingest_upload(
        revision.source_id,
        method=SourceIngestionMethod.JSON,
        filename="changed.json",
        content=b'{"fixture": true, "text": "changed candidate"}',
        actor_id="test",
    )
    assert revision.status == "active"
    assert service.curriculum_path(node.id) == old_path
    with pytest.raises(ValueError):
        service.upsert_nodes(version=version, revision=candidate, specs=[grade()])
    service.source_service.extract_revision(candidate.id, actor_id="test")
    service.source_service.create_diff(candidate.id, actor_id="test")
    assert service.source_service.validate_revision(candidate.id, actor_id="test").valid
    service.source_service.approve_revision(candidate.id, actor_id="test")
    service.source_service.activate_revision(candidate.id, actor_id="test")
    assert revision.status == "superseded"
    with pytest.raises(ValueError):
        service.upsert_nodes(version=version, revision=revision, specs=[grade()])
    assert service.curriculum_path(node.id) == old_path


def test_superseded_version_is_read_only(service: CurriculumIntelligenceService) -> None:
    version, revision = scoped(service)
    service.supersede_version(version)
    with pytest.raises(ValueError, match="read-only"):
        service.upsert_nodes(version=version, revision=revision, specs=[grade()])


def test_same_revision_cannot_rewrite_official_node_wording(
    service: CurriculumIntelligenceService,
) -> None:
    version, revision = scoped(service)
    original = grade(title="తెలుగు اردو हिन्दी")
    node = service.upsert_nodes(version=version, revision=revision, specs=[original])[original.code]
    with pytest.raises(ValueError, match="immutable"):
        service.upsert_nodes(
            version=version,
            revision=revision,
            specs=[original.model_copy(update={"title": "changed"})],
        )
    service.session.commit()
    service.session.expire_all()
    persisted = service.session.get(CurriculumNode, node.id)
    assert persisted is not None and persisted.title == original.title


@pytest.mark.parametrize("kind", ["node", "outcome", "standard"])
def test_unicode_replacement_character_cannot_be_written(
    service: CurriculumIntelligenceService, kind: str
) -> None:
    version, revision = scoped(service)
    with pytest.raises(ValueError):
        if kind == "node":
            service.upsert_nodes(
                version=version, revision=revision, specs=[grade(title="తెలు\ufffdగు")]
            )
        elif kind == "outcome":
            revision = synthetic_revision(
                service,
                pack=version.curriculum_pack.code,
                domain="learning_outcomes",
                grades=("First Year", "Second Year"),
            )
            service.upsert_learning_outcomes(
                version=version,
                revision=revision,
                specs=[
                    LearningOutcomeSpec(
                        code="corrupt",
                        text="తెలు\ufffdగు",
                        metadata_json=identity(),
                        source_locator="JSON pointer /text",
                    )
                ],
            )
        else:
            revision = synthetic_revision(
                service,
                pack=version.curriculum_pack.code,
                domain="academic_standard",
                grades=("First Year", "Second Year"),
            )
            service.upsert_competencies(
                framework=None,
                curriculum_version=version,
                revision=revision,
                specs=[
                    CompetencySpec(
                        code="corrupt",
                        name="తెలు\ufffdగు",
                        metadata_json=identity(),
                        source_locator="JSON pointer /text",
                    )
                ],
            )


@pytest.mark.parametrize("tamper", ["bytes", "snapshot", "approval"])
def test_exact_source_integrity_is_rechecked_at_write(
    service: CurriculumIntelligenceService, tamper: str
) -> None:
    version, revision = scoped(service)
    if tamper == "bytes":
        assert revision.storage_path
        (service.source_service.storage.root / revision.storage_path).write_bytes(b"tampered bytes")
    elif tamper == "snapshot":
        metadata = copy.deepcopy(revision.metadata_json)
        metadata["source_snapshot"]["metadata_json"]["curriculum_scope"]["grades"].append("XI")
        revision.metadata_json = metadata
    else:
        assert revision.extracted_text is not None
        revision.extracted_text += "\nchanged after review"
    with pytest.raises(ValueError, match="integrity|checksum|approval"):
        service.upsert_nodes(version=version, revision=revision, specs=[grade()])


def test_foreign_learning_outcome_source_and_target_cannot_autoalign(
    service: CurriculumIntelligenceService,
) -> None:
    version, _ = scoped(service)
    foreign, _ = scoped(service, "synthetic-ncert-like")
    foreign_revision = synthetic_revision(
        service,
        pack=foreign.curriculum_pack.code,
        domain="learning_outcomes",
        grades=("First Year", "Second Year"),
    )
    with pytest.raises(ValueError):
        service.upsert_learning_outcomes(
            version=version,
            revision=foreign_revision,
            specs=[
                LearningOutcomeSpec(
                    code="foreign",
                    text="Synthetic outcome",
                    metadata_json=identity(),
                    source_locator="JSON pointer /text",
                )
            ],
        )
    target = service.session.scalar(
        select(LearningOutcome).where(LearningOutcome.curriculum_version_id == foreign.id)
    )
    node = service.session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id,
            CurriculumNode.code == "first-year-english-concept",
        )
    )
    own_revision = synthetic_revision(
        service,
        pack=version.curriculum_pack.code,
        domain="learning_outcomes",
        grades=("First Year", "Second Year"),
    )
    assert target is not None and node is not None
    with pytest.raises(ValueError):
        service.align(
            CurriculumAlignmentInput(
                curriculum_version_id=version.id,
                curriculum_node_id=node.id,
                learning_outcome_id=target.id,
                source_revision_id=own_revision.id,
                relationship_type="addresses",
                status="partial",
                inferred=True,
                source_locator="JSON pointer /text",
            )
        )


def concept(
    service: CurriculumIntelligenceService, version: CurriculumVersion, code: str
) -> CurriculumNode:
    node = service.session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id, CurriculumNode.code == code
        )
    )
    assert node is not None
    return node


@pytest.mark.parametrize("dimension", ["pack_code", "version_code", "grade", "medium", "subject"])
def test_lookup_never_defaults_missing_scope(
    service: CurriculumIntelligenceService, dimension: str
) -> None:
    version, _ = scoped(service)
    args: dict[str, Any] = {
        "pack_code": version.curriculum_pack.code,
        "version_code": version.version_code,
        "grade": "First Year",
        "medium": "English",
        "subject": "science",
    }
    for absent in (None, "unknown"):
        result = query_scoped_paths(service, **(args | {dimension: absent}))
        assert result == {"status": "unknown_scope", "paths": []}


def test_lookup_constrains_each_dimension_and_historical_flag(
    service: CurriculumIntelligenceService,
) -> None:
    version, _ = scoped(service)
    args: dict[str, Any] = {
        "pack_code": version.curriculum_pack.code,
        "version_code": version.version_code,
        "grade": "First Year",
        "medium": "English",
        "subject": "science",
    }
    expected = concept(service, version, "first-year-english-concept")
    matched = query_scoped_paths(service, **args)
    assert matched["status"] == "matched"
    assert len(matched["paths"]) == 1
    assert matched["paths"][0]["node_ids"][-1] == expected.id
    for field, value in [
        ("pack_code", "other"),
        ("version_code", "2026-27"),
        ("grade", "XI"),
        ("medium", "Urdu"),
        ("subject", "mathematics"),
    ]:
        assert query_scoped_paths(service, **(args | {field: value}))["paths"] == []
    second = query_scoped_paths(service, **(args | {"grade": "Second Year"}))
    assert second["paths"][0]["node_ids"][-1] != expected.id
    service.supersede_version(version)
    assert query_scoped_paths(service, **args)["status"] == "historical_only"
    historical = query_scoped_paths(service, **args, include_historical=True)
    assert historical["paths"] == matched["paths"]
    assert historical["version_status"] == "superseded"


def test_reviewed_cross_medium_correspondence_is_exact_idempotent_and_persistent(
    service: CurriculumIntelligenceService,
) -> None:
    version, _ = scoped(service)
    left = concept(service, version, "first-year-english-concept")
    right = concept(service, version, "first-year-telugu-concept")
    declaration = {
        "left_code": left.code,
        "right_code": right.code,
        "locator": "JSON pointer /text",
        "evidence_text": "source evidence",
    }
    revision = approved_revision(
        service,
        pack=version.curriculum_pack.code,
        grades=("First Year", "Second Year"),
        media=("English", "Telugu"),
        declarations=[declaration],
        non_applicable_dimensions=True,
    )
    kwargs: dict[str, Any] = {
        "left_node_id": left.id,
        "right_node_id": right.id,
        "revision": revision,
        "locator": declaration["locator"],
        "evidence_text": declaration["evidence_text"],
    }
    key = link_correspondence(service, version, **kwargs)
    assert link_correspondence(service, version, **kwargs) == key
    service.session.commit()
    service.session.expire_all()
    assert len(version.metadata_json["cross_medium_correspondences"]) == 1
    record = version.metadata_json["cross_medium_correspondences"][key]
    assert record["source_revision_id"] == revision.id
    assert record["source_checksum"] == revision.checksum
    assert record["left_id"] == left.id and record["right_id"] == right.id
    for field, value in [
        ("locator", "guessed page"),
        ("evidence_text", "generated translation"),
        ("right_node_id", concept(service, version, "second-year-telugu-concept").id),
        ("right_node_id", left.id),
    ]:
        with pytest.raises(ValueError):
            link_correspondence(service, version, **(kwargs | {field: value}))
    assert len(version.metadata_json["cross_medium_correspondences"]) == 1


def test_matching_titles_never_imply_correspondence(service: CurriculumIntelligenceService) -> None:
    version, revision = scoped(service)
    left = concept(service, version, "first-year-english-concept")
    right = concept(service, version, "first-year-telugu-concept")
    assert left.title == right.title
    with pytest.raises(ValueError, match="declaration"):
        link_correspondence(
            service,
            version,
            left_node_id=left.id,
            right_node_id=right.id,
            revision=revision,
            locator="synthetic JSON",
            evidence_text="synthetic evidence",
        )


def test_existing_draft_cannot_be_activated_by_ensure_version(
    service: CurriculumIntelligenceService,
) -> None:
    version, revision = scoped(service)
    with pytest.raises(ValueError, match="Draft|unverified"):
        service.ensure_version(
            pack=version.curriculum_pack,
            version_code=version.version_code,
            academic_year=version.academic_year,
            revision=revision,
            source_locator=version.source_locator,
            metadata_json=version.metadata_json,
            active=True,
        )
    assert version.status == "draft"


@pytest.mark.parametrize("kind", ["outcome", "standard"])
def test_same_revision_cannot_rewrite_outcome_or_standard(
    service: CurriculumIntelligenceService, kind: str
) -> None:
    version, _ = scoped(service)
    domain = "learning_outcomes" if kind == "outcome" else "academic_standard"
    revision = synthetic_revision(
        service,
        pack=version.curriculum_pack.code,
        domain=domain,
        grades=("First Year", "Second Year"),
    )
    with pytest.raises(ValueError):
        if kind == "outcome":
            service.upsert_learning_outcomes(
                version=version,
                revision=revision,
                specs=[
                    LearningOutcomeSpec(
                        code="synthetic-lo",
                        text="changed official outcome",
                        source_locator="JSON pointer /text",
                        metadata_json=identity(),
                    )
                ],
            )
        else:
            service.upsert_competencies(
                framework=None,
                curriculum_version=version,
                revision=revision,
                specs=[
                    CompetencySpec(
                        code=version.curriculum_pack.code + "-standard",
                        name="Changed standard",
                        official_text="తెలుగు ప్రమాణం",
                        source_locator="JSON pointer /text",
                        metadata_json=identity(),
                    )
                ],
            )


@pytest.mark.parametrize("case", ["missing", "cycle", "duplicate", "cross_version"])
def test_invalid_hierarchy_cannot_write(service: CurriculumIntelligenceService, case: str) -> None:
    version, revision = scoped(service)
    spec = CurriculumNodeSpec(
        node_type="unit",
        code="unwritable",
        title="Unit",
        parent_code="absent-subject",
        source_locator="JSON pointer /text",
        metadata_json=identity(),
    )
    specs = [spec]
    if case == "cycle":
        specs = [
            spec.model_copy(update={"parent_code": "cycle-peer"}),
            spec.model_copy(update={"code": "cycle-peer", "parent_code": "unwritable"}),
        ]
    elif case == "duplicate":
        specs = [spec, spec]
    elif case == "cross_version":
        foreign, foreign_revision = scoped(service, "synthetic-foreign-parent")
        service.upsert_nodes(
            version=foreign, revision=foreign_revision, specs=[grade(code="only-foreign-parent")]
        )
        specs = [
            CurriculumNodeSpec(
                node_type="medium",
                code="unwritable",
                title="English",
                parent_code="only-foreign-parent",
                source_locator="JSON pointer /text",
                metadata_json={"identity": {"grade": "First Year", "medium": "English"}},
            )
        ]
    with pytest.raises(ValueError, match="missing parents|cycle|unique"):
        service.upsert_nodes(version=version, revision=revision, specs=specs)
    assert (
        service.session.scalar(
            select(CurriculumNode).where(
                CurriculumNode.curriculum_version_id == version.id,
                CurriculumNode.code == "unwritable",
            )
        )
        is None
    )


def test_scoped_source_cannot_escape_guards_by_omitting_metadata(
    service: CurriculumIntelligenceService,
) -> None:
    revision = approved_revision(service)
    pack = service.ensure_pack(
        framework=None,
        code="synthetic-active",
        name="Synthetic",
        authority="Synthetic",
        country="India",
        revision=revision,
    )
    assert pack.metadata_json["scope_enforced"] is True
    version = service.ensure_version(
        pack=pack,
        version_code="synthetic-2025-26",
        academic_year="2025-26",
        revision=revision,
        active=False,
    )
    assert version.metadata_json["scope_enforced"] is True
    with pytest.raises(ValueError):
        service.upsert_nodes(version=version, revision=revision, specs=[grade(identity="VIII")])
    with pytest.raises(ValueError):
        service.ensure_version(
            pack=pack,
            version_code="synthetic-2025-26",
            academic_year="2025-26",
            revision=revision,
            active=True,
        )
    assert version.status == "draft"


def test_pack_creation_rejects_wrong_source_identity(
    service: CurriculumIntelligenceService,
) -> None:
    revision = approved_revision(service)
    with pytest.raises(ValueError, match="pack|scope"):
        service.ensure_pack(
            framework=None,
            code="another-board",
            name="Synthetic",
            authority="Synthetic",
            country="India",
            revision=revision,
        )
    assert (
        service.session.scalar(select(CurriculumPack).where(CurriculumPack.code == "another-board"))
        is None
    )


@pytest.mark.parametrize("wrong", [False, True])
def test_correspondence_wording_is_bound_to_claimed_section(service, wrong):
    version, _ = scoped(service)
    left = concept(service, version, "first-year-english-concept")
    right = concept(service, version, "first-year-telugu-concept")
    words = f"{left.code} corresponds to {right.code}"
    locator = "JSON pointer /sections/" + ("A" if wrong else "B")
    declaration = {
        "left_code": left.code,
        "right_code": right.code,
        "locator": locator,
        "evidence_text": words,
    }
    revision = approved_revision(
        service,
        pack=version.curriculum_pack.code,
        grades=("First Year", "Second Year"),
        media=("English", "Telugu"),
        declarations=[declaration],
        non_applicable_dimensions=True,
        content={"sections": {"A": "Unrelated source context", "B": words}},
    )
    args = dict(
        left_node_id=left.id,
        right_node_id=right.id,
        revision=revision,
        locator=locator,
        evidence_text=words,
    )
    if wrong:
        with pytest.raises(ValueError, match="absent at exact locator"):
            link_correspondence(service, version, **args)
        assert not version.metadata_json.get("cross_medium_correspondences")
    else:
        key = link_correspondence(service, version, **args)
        assert link_correspondence(service, version, **args) == key


@pytest.mark.parametrize(
    "fault", ["none", "wrong-section", "target-wording", "ancestor-wording", "ambiguous-code"]
)
def test_scoped_direct_alignment_uses_bounded_source_and_own_target_proof(service, fault):
    from app.models.curriculum_intelligence import CurriculumAlignment

    version, _ = scoped(service)
    node = concept(service, version, "first-year-english-concept")
    outcome = service.session.scalar(
        select(LearningOutcome).where(LearningOutcome.curriculum_version_id == version.id)
    )
    assert outcome is not None
    words = f"{node.code} directly addresses {outcome.code}"
    locator = "JSON pointer /sections/" + ("A" if fault == "wrong-section" else "B")
    declaration = {
        "node_code": node.code,
        "target_id": outcome.id,
        "relationship_type": "addresses",
        "source_locator": locator,
        "evidence_text": words,
    }
    revision = approved_revision(
        service,
        pack=version.curriculum_pack.code,
        grades=("First Year", "Second Year"),
        media=("English", "Telugu"),
        alignments=[declaration],
        non_applicable_dimensions=True,
        content={"sections": {"A": "Unrelated source context", "B": words}},
    )
    if fault == "target-wording":
        outcome.text = "Invented outcome"
    elif fault == "ancestor-wording":
        service.hierarchy_path(node.id)[0].official_text = "Invented ancestor quote"
    elif fault == "ambiguous-code":
        concept(service, version, "first-year-telugu-concept").code = node.code
    service.session.flush()
    payload = CurriculumAlignmentInput(
        curriculum_version_id=version.id,
        curriculum_node_id=node.id,
        learning_outcome_id=outcome.id,
        source_revision_id=revision.id,
        status="direct",
        relationship_type="addresses",
        source_locator=locator,
        evidence_text=words,
    )
    before = list(service.session.scalars(select(CurriculumAlignment.id)))
    if fault != "none":
        with pytest.raises(ValueError):
            service.align(payload)
        assert list(service.session.scalars(select(CurriculumAlignment.id))) == before
    else:
        link = service.align(payload)
        assert service.align(payload).id == link.id
        assert link.evidence_text == words and link.source_locator == locator
