"""Adversarial synthetic snapshots prove document-purpose boundaries, not official evidence."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.curriculum_intelligence.framework_structure import (
    FrameworkStructureError,
    FrameworkStructureService,
)
from app.curriculum_intelligence.service import (
    CurriculumIntelligenceError,
    CurriculumIntelligenceService,
)
from app.curriculum_intelligence.source_domains import (
    DOCUMENT_DOMAINS,
    require_domain,
    source_domain,
)
from app.day4_verify import seed_day4_verification
from app.db.base import Base
from app.models.curriculum import Competency, CurriculumPack, CurriculumVersion, EducationFramework
from app.models.source import SourceRevision
from app.schemas.framework_structure import FrameworkNodeSpec, LearningOutcomeCompetencyInput


@pytest.fixture
def seeded() -> Iterator[tuple[Session, dict[str, Any]]]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session, seed_day4_verification(session)
    engine.dispose()


def _change_domain(session: Session, revision: SourceRevision, document_type: str) -> None:
    snapshot = dict(revision.metadata_json.get("source_snapshot", {}))
    metadata = dict(snapshot.get("metadata_json", {}))
    metadata.pop("source_domain", None)
    metadata["document_type"] = document_type
    snapshot["metadata_json"] = metadata
    revision.metadata_json = dict(revision.metadata_json) | {"source_snapshot": snapshot}
    session.flush()


@pytest.mark.parametrize("document_type", list(DOCUMENT_DOMAINS))
def test_every_supported_document_type_has_explicit_semantics(document_type: str) -> None:
    snapshot = {"metadata_json": {"document_type": document_type}}
    assert source_domain(snapshot) == DOCUMENT_DOMAINS[document_type]
    if DOCUMENT_DOMAINS[document_type] == "syllabus":
        require_domain(snapshot, "membership")
    else:
        with pytest.raises(ValueError, match="cannot establish membership"):
            require_domain(snapshot, "membership")


def test_unknown_conflicting_and_legacy_domains() -> None:
    require_domain({}, "membership")
    with pytest.raises(ValueError, match="unknown document"):
        require_domain({"metadata_json": {"document_type": "unrecognized"}}, "membership")
    with pytest.raises(ValueError, match="conflicting"):
        require_domain(
            {"metadata_json": {"document_type": "textbook", "source_domain": "syllabus"}},
            "membership",
        )
    assert (
        source_domain(
            {"source_type": "sample_paper", "metadata_json": {"document_type": "syllabus"}}
        )
        == "assessment"
    )


@pytest.mark.parametrize(
    "document_type",
    [
        "textbook",
        "teacher_handbook",
        "academic_calendar",
        "learning_outcomes",
        "academic_standards",
        "sample_question_paper",
        "model_paper",
    ],
)
def test_non_governing_documents_cannot_write_any_membership_surface(
    seeded: tuple[Session, dict[str, Any]],
    document_type: str,
) -> None:
    session, result = seeded
    service = CurriculumIntelligenceService(session)
    version = session.get(CurriculumVersion, result["curriculum"]["version_id"])
    pack = session.get(CurriculumPack, result["curriculum"]["pack_id"])
    framework = session.get(EducationFramework, result["framework"]["id"])
    assert version is not None and pack is not None and framework is not None
    revision = session.get(SourceRevision, version.source_revision_id)
    assert revision is not None
    _change_domain(session, revision, document_type)
    before = dict(version.metadata_json)
    with pytest.raises(CurriculumIntelligenceError, match="cannot establish"):
        service.upsert_nodes(version=version, specs=[], revision=revision)
    with pytest.raises(CurriculumIntelligenceError, match="cannot establish"):
        service.ensure_pack(
            framework=framework,
            code="must-not-exist",
            name="Invalid",
            country="India",
            authority="Synthetic",
            revision=revision,
        )
    with pytest.raises(CurriculumIntelligenceError, match="cannot establish"):
        service.ensure_version(
            pack=pack, version_code="must-not-exist", academic_year="unknown", revision=revision
        )
    assert version.metadata_json == before


@pytest.mark.parametrize(
    "document_type",
    [
        "textbook",
        "teacher_handbook",
        "academic_calendar",
        "learning_outcomes",
        "academic_standards",
        "sample_question_paper",
        "model_paper",
    ],
)
def test_framework_structure_and_root_creation_reject_wrong_semantic_domains(
    seeded: tuple[Session, dict[str, Any]],
    document_type: str,
) -> None:
    session, result = seeded
    framework = session.get(EducationFramework, result["framework"]["id"])
    assert framework is not None
    revision = session.get(SourceRevision, framework.source_revision_id)
    assert revision is not None
    _change_domain(session, revision, document_type)
    if document_type == "academic_standards":
        # Standards may describe goals/competencies inside an existing framework,
        # but cannot establish a new framework or syllabus membership.
        FrameworkStructureService(session).upsert_nodes(
            framework=framework, revision=revision, specs=[]
        )
    else:
        with pytest.raises(FrameworkStructureError, match="cannot establish"):
            FrameworkStructureService(session).upsert_nodes(
                framework=framework, revision=revision, specs=[]
            )
    with pytest.raises(CurriculumIntelligenceError, match="cannot establish"):
        CurriculumIntelligenceService(session).ensure_framework(
            code="must-not-exist",
            name="Invalid",
            country="India",
            authority="Synthetic",
            version_code="unknown",
            revision=revision,
        )


@pytest.mark.parametrize(
    "document_type", ["learning_outcomes", "academic_standards", "subject_syllabus"]
)
def test_outcome_domain_can_link_existing_competency_without_creating_framework(
    seeded: tuple[Session, dict[str, Any]],
    document_type: str,
) -> None:
    session, result = seeded
    framework = session.get(EducationFramework, result["framework"]["id"])
    assert framework is not None
    revision = session.get(SourceRevision, framework.source_revision_id)
    assert revision is not None
    structure = FrameworkStructureService(session)
    specs = [
        FrameworkNodeSpec(
            source_locator="synthetic table",
            publication_status="draft",
            level="stage",
            code="stage",
            title="Stage",
        ),
        FrameworkNodeSpec(
            source_locator="synthetic table",
            publication_status="draft",
            level="curricular_area",
            code="area",
            title="Area",
            parent_code="stage",
        ),
        FrameworkNodeSpec(
            source_locator="synthetic table",
            publication_status="draft",
            level="goal",
            code="goal",
            title="Goal",
            parent_code="area",
        ),
        FrameworkNodeSpec(
            source_locator="synthetic table",
            publication_status="draft",
            level="competency",
            code="competency",
            title="Competency",
            parent_code="goal",
            competency_id=result["competency"]["id"],
        ),
    ]
    structure.upsert_nodes(framework=framework, revision=revision, specs=specs[:3])
    competency = session.get(Competency, result["competency"]["id"])
    assert competency is not None
    competency_revision = session.get(SourceRevision, competency.source_revision_id)
    assert competency_revision is not None
    nodes = structure.upsert_nodes(
        framework=framework, revision=competency_revision, specs=specs[3:]
    )
    _change_domain(session, revision, document_type)
    payload = LearningOutcomeCompetencyInput.model_validate(
        {
            "curriculum_version_id": result["curriculum"]["version_id"],
            "learning_outcome_id": result["learning_outcome"]["id"],
            "competency_node_id": nodes["competency"].id,
            "source_revision_id": revision.id,
            "source_locator": "synthetic mapping",
            "publication_status": "draft",
            "status": "partial",
            "inferred": True,
        }
    )
    link = structure.link_learning_outcome(payload)
    assert link.source_revision_id == revision.id
    assert link.inferred
    if document_type == "learning_outcomes":
        with pytest.raises(FrameworkStructureError, match="cannot establish framework"):
            structure.upsert_nodes(framework=framework, revision=revision, specs=[])


@pytest.mark.parametrize(
    "document_type", ["textbook", "teacher_handbook", "academic_calendar", "sample_question_paper"]
)
def test_wrong_domains_rejected_before_learning_outcome_link_target_lookup(
    seeded: tuple[Session, dict[str, Any]],
    document_type: str,
) -> None:
    session, result = seeded
    revision = session.get(SourceRevision, result["learning_outcome"]["source_revision_id"])
    assert revision is not None
    _change_domain(session, revision, document_type)
    payload = LearningOutcomeCompetencyInput.model_validate(
        {
            "curriculum_version_id": result["curriculum"]["version_id"],
            "learning_outcome_id": result["learning_outcome"]["id"],
            "competency_node_id": result["competency"]["id"],
            "source_revision_id": revision.id,
            "source_locator": "synthetic mapping",
            "publication_status": "draft",
            "status": "partial",
            "inferred": True,
        }
    )
    with pytest.raises(FrameworkStructureError, match="cannot establish"):
        FrameworkStructureService(session).link_learning_outcome(payload)
