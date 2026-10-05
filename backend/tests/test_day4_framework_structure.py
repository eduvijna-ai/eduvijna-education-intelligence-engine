"""Synthetic framework data verifies generic contracts, not official curriculum completeness."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401
from app.curriculum_intelligence.framework_structure import (
    FrameworkStructureError,
    FrameworkStructureService,
)
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.curriculum import (
    Competency,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
    LearningOutcome,
)
from app.models.framework_structure import FrameworkStructureNode, LearningOutcomeCompetencyLink
from app.models.source import Source, SourceRevision
from app.schemas.framework_structure import FrameworkNodeSpec, LearningOutcomeCompetencyInput


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
    create_database_engine.cache_clear()


@dataclass
class Context:
    framework: EducationFramework
    revision: SourceRevision
    competency: Competency
    version: CurriculumVersion
    outcome: LearningOutcome


def _context(db: Session, suffix: str = "one") -> Context:
    source = Source(source_type="official_authority", title=f"Synthetic test source {suffix}")
    db.add(source)
    db.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="a" * 64,
        source_snapshot_checksum="b" * 64,
        ingestion_method="upload",
        content_type="text/plain",
        byte_size=24,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_text="Synthetic test evidence.",
        extracted_checksum="a" * 64,
        metadata_json={"synthetic": True},
    )
    db.add(revision)
    db.flush()
    framework = EducationFramework(
        code=f"synthetic-framework-{suffix}",
        name="Synthetic framework",
        country="Test",
        version_code="2023-draft",
        source_revision_id=revision.id,
    )
    db.add(framework)
    db.flush()
    pack = CurriculumPack(
        framework_id=framework.id,
        code=f"synthetic-pack-{suffix}",
        name="Synthetic pack",
        country="Test",
        source_revision_id=revision.id,
    )
    db.add(pack)
    db.flush()
    version = CurriculumVersion(
        curriculum_pack_id=pack.id,
        version_code="2026-27",
        source_revision_id=revision.id,
    )
    competency = Competency(
        framework_id=framework.id,
        code=f"synthetic-C3.2-{suffix}",
        name="Synthetic competency",
        source_revision_id=revision.id,
    )
    db.add_all([version, competency])
    db.flush()
    outcome = LearningOutcome(
        curriculum_version_id=version.id,
        code="synthetic-lo",
        text="Synthetic learning outcome",
        source_revision_id=revision.id,
    )
    db.add(outcome)
    db.flush()
    return Context(framework, revision, competency, version, outcome)


def _specs(context: Context) -> list[FrameworkNodeSpec]:
    common: dict[str, Any] = {
        "publication_status": "draft",
        "review_status": "reviewed",
        "source_locator": "p. 4",
    }
    return [
        FrameworkNodeSpec(level="stage", code="secondary", title="Secondary", **common),
        FrameworkNodeSpec(
            level="curricular_area",
            code="mathematics",
            title="Mathematics",
            parent_code="secondary",
            **common,
        ),
        FrameworkNodeSpec(
            level="goal",
            code="CG3",
            title="Synthetic curricular goal",
            parent_code="mathematics",
            official_code="CG3",
            **common,
        ),
        FrameworkNodeSpec(
            level="competency",
            code="C3.2",
            title="Synthetic competency",
            parent_code="CG3",
            official_code="C3.2",
            competency_id=UUID(context.competency.id),
            official_text="Synthetic official-text field; not official content.",
            **common,
        ),
    ]


def _tree(db: Session, context: Context) -> dict[str, FrameworkStructureNode]:
    return FrameworkStructureService(db).upsert_nodes(
        framework=context.framework, revision=context.revision, specs=_specs(context)
    )


def _link_input(context: Context, node_id: str, **changes: Any) -> LearningOutcomeCompetencyInput:
    values = {
        "curriculum_version_id": context.version.id,
        "learning_outcome_id": context.outcome.id,
        "competency_node_id": node_id,
        "source_revision_id": context.revision.id,
        "source_locator": "p. 8, synthetic mapping",
        "publication_status": "draft",
        "review_status": "reviewed",
        "status": "partial",
        "inferred": True,
    }
    values.update(changes)
    return LearningOutcomeCompetencyInput.model_validate(values)


def test_typed_framework_path_and_explicit_outcome_link_are_idempotent(db: Session) -> None:
    context = _context(db)
    service = FrameworkStructureService(db)
    first = _tree(db, context)
    second = service.upsert_nodes(
        framework=context.framework, revision=context.revision, specs=reversed(_specs(context))
    )
    assert {key: node.id for key, node in first.items()} == {
        key: node.id for key, node in second.items()
    }
    payload = _link_input(context, first["C3.2"].id)
    link = service.link_learning_outcome(payload)
    assert service.link_learning_outcome(payload).id == link.id
    result = service.path_for_competency(first["C3.2"].id, curriculum_version_id=context.version.id)
    assert [node.level for node in result.nodes] == [
        "stage",
        "curricular_area",
        "goal",
        "competency",
    ]
    assert result.framework_version_code == "2023-draft"
    assert result.nodes[-1].competency_id == UUID(context.competency.id)
    assert result.nodes[-1].official_code == "C3.2"
    assert result.nodes[-1].official_text != result.nodes[-1].title
    assert all(node.publication_status == "draft" for node in result.nodes)
    assert all(node.review_status == "reviewed" for node in result.nodes)
    assert all(node.source_revision_id == UUID(context.revision.id) for node in result.nodes)
    assert all(node.source_locator == "p. 4" for node in result.nodes)
    assert result.learning_outcome_links[0].learning_outcome_id == UUID(context.outcome.id)
    assert result.learning_outcome_links[0].inferred is True
    assert result.learning_outcome_links[0].status == "partial"
    assert result.learning_outcome_links[0].publication_status == "draft"
    assert len(service.list_nodes(context.framework.id, level="goal")) == 1
    assert db.scalar(select(func.count(FrameworkStructureNode.id))) == 4
    assert db.scalar(select(func.count(LearningOutcomeCompetencyLink.id))) == 1


@pytest.mark.parametrize("status", ["staged", "extracted", "validated", "approved", "superseded"])
def test_all_writes_require_active_revision_but_historical_reads_work(
    db: Session, status: str
) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    service = FrameworkStructureService(db)
    payload = _link_input(context, nodes["C3.2"].id)
    service.link_learning_outcome(payload)
    context.revision.status = status
    context.revision.active_slot = None
    db.flush()
    with pytest.raises(FrameworkStructureError, match="active SourceRevision"):
        service.upsert_nodes(
            framework=context.framework, revision=context.revision, specs=_specs(context)
        )
    with pytest.raises(FrameworkStructureError, match="active SourceRevision"):
        service.link_learning_outcome(payload)
    assert len(service.path_for_competency(nodes["C3.2"].id).nodes) == 4
    assert len(service.list_nodes(context.framework.id)) == 4


def test_source_change_and_silent_content_changes_preserve_existing_evidence(db: Session) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    service = FrameworkStructureService(db)
    other = _context(db, "other")
    with pytest.raises(FrameworkStructureError, match="cannot silently rebind"):
        service.upsert_nodes(
            framework=context.framework, revision=other.revision, specs=_specs(context)
        )
    changed = _specs(context)[0].model_copy(update={"title": "Changed claim"})
    with pytest.raises(FrameworkStructureError, match="immutable"):
        service.upsert_nodes(
            framework=context.framework, revision=context.revision, specs=[changed]
        )
    stored = db.get(FrameworkStructureNode, nodes["secondary"].id)
    assert stored is not None and stored.title == "Secondary"
    payload = _link_input(context, nodes["C3.2"].id)
    service.link_learning_outcome(payload)
    with pytest.raises(FrameworkStructureError, match="immutable"):
        service.link_learning_outcome(payload.model_copy(update={"source_locator": "changed"}))


@pytest.mark.parametrize("level", ["chapter", "unknown", "", "Stage"])
def test_unknown_standard_levels_rejected(level: str) -> None:
    with pytest.raises(ValidationError):
        FrameworkNodeSpec.model_validate(
            {
                "level": level,
                "code": "test",
                "title": "Test",
                "publication_status": "final",
                "source_locator": "p. 1",
            }
        )


@pytest.mark.parametrize("level,competency", [("competency", None), ("stage", uuid4())])
def test_only_competency_leaves_reference_registry(level: str, competency: UUID | None) -> None:
    with pytest.raises(ValidationError):
        FrameworkNodeSpec.model_validate(
            {
                "level": level,
                "code": "test",
                "title": "Test",
                "publication_status": "final",
                "source_locator": "p. 1",
                "competency_id": competency,
            }
        )


@pytest.mark.parametrize("case", ["duplicate", "missing", "wrong_level", "self", "cycle"])
def test_invalid_framework_hierarchy_is_atomic(db: Session, case: str) -> None:
    context = _context(db)
    specs = _specs(context)
    if case == "duplicate":
        specs.append(specs[0])
    elif case == "missing":
        specs[2] = specs[2].model_copy(update={"parent_code": "absent"})
    elif case == "wrong_level":
        specs[2] = specs[2].model_copy(update={"parent_code": "secondary"})
    elif case == "self":
        specs[2] = specs[2].model_copy(update={"parent_code": "CG3"})
    else:
        specs[0] = specs[0].model_copy(update={"parent_code": "C3.2"})
    with pytest.raises(FrameworkStructureError):
        FrameworkStructureService(db).upsert_nodes(
            framework=context.framework, revision=context.revision, specs=specs
        )
    assert db.scalar(select(func.count(FrameworkStructureNode.id))) == 0


def test_cross_framework_parent_and_competency_are_rejected(db: Session) -> None:
    context = _context(db)
    other = _context(db, "other")
    _tree(db, other)
    service = FrameworkStructureService(db)
    with pytest.raises(FrameworkStructureError, match="cross-framework parent"):
        service.upsert_nodes(
            framework=context.framework, revision=context.revision, specs=[_specs(context)[1]]
        )
    specs = _specs(context)
    specs[-1] = specs[-1].model_copy(update={"competency_id": UUID(other.competency.id)})
    with pytest.raises(FrameworkStructureError, match="cross-framework competency"):
        service.upsert_nodes(framework=context.framework, revision=context.revision, specs=specs)


def test_outcome_wrong_version_wrong_framework_and_noncompetency_targets_rejected(
    db: Session,
) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    other = _context(db, "other")
    other_nodes = _tree(db, other)
    service = FrameworkStructureService(db)
    with pytest.raises(FrameworkStructureError, match="different curriculum version"):
        service.link_learning_outcome(
            _link_input(context, nodes["C3.2"].id, curriculum_version_id=other.version.id)
        )
    with pytest.raises(FrameworkStructureError, match="cross-framework target"):
        service.link_learning_outcome(_link_input(context, other_nodes["C3.2"].id))
    with pytest.raises(FrameworkStructureError, match="competency-level"):
        service.link_learning_outcome(_link_input(context, nodes["CG3"].id))
    with pytest.raises(FrameworkStructureError, match="different framework"):
        service.path_for_competency(nodes["C3.2"].id, curriculum_version_id=other.version.id)
    assert db.scalar(select(func.count(LearningOutcomeCompetencyLink.id))) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"inferred": True},
        {"review_status": "review_required"},
        {"evidence_text": None},
    ],
)
def test_direct_assertions_require_review_and_source_evidence(changes: dict[str, Any]) -> None:
    values = {
        "curriculum_version_id": uuid4(),
        "learning_outcome_id": uuid4(),
        "competency_node_id": uuid4(),
        "source_revision_id": uuid4(),
        "source_locator": "p. 1",
        "publication_status": "draft",
        "review_status": "reviewed",
        "status": "direct",
        "inferred": False,
        "evidence_text": "Synthetic source statement",
    }
    values.update(changes)
    with pytest.raises(ValidationError):
        LearningOutcomeCompetencyInput.model_validate(values)


def _direct_context(
    db: Session, tmp_path: Path, *, scope: dict[str, Any] | None = None
) -> tuple[Context, FrameworkStructureService, dict[str, FrameworkStructureNode]]:
    import json

    from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
    from app.schemas.source_intelligence import SourceRegistrationInput
    from app.source_intelligence.service import SourceIntelligenceService
    from app.source_intelligence.storage import LocalSourceStorage

    context = _context(db)
    sources = SourceIntelligenceService(db, storage=LocalSourceStorage(tmp_path / "sources"))
    source = sources.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_AUTHORITY,
            title="Synthetic direct mapping fixture",
            url="https://synthetic.invalid/framework.json",
            authority="Synthetic",
            country="Test",
            copyright_classification="synthetic_fixture",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "synthetic": True,
                "document_type": "education_framework",
                **({"curriculum_scope": scope} if scope is not None else {}),
            },
        ),
        actor_id="test",
    )
    revision = sources.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="direct.json",
        content=json.dumps(
            {
                "mapping": "Synthetic learning outcome maps to Synthetic competency C3.2.",
                "unrelated": "Another outcome maps to C9.9.",
            }
        ).encode(),
        actor_id="test",
    )
    sources.extract_revision(revision.id, actor_id="test")
    sources.create_diff(revision.id, actor_id="test")
    assert sources.validate_revision(revision.id, actor_id="test").valid
    sources.approve_revision(revision.id, actor_id="test")
    context.revision = sources.activate_revision(revision.id, actor_id="test")
    for entity in (context.framework, context.version, context.competency, context.outcome):
        entity.source_revision_id = revision.id
    context.outcome.source_locator = "JSON pointer /mapping"
    context.competency.source_locator = "JSON pointer /mapping"
    context.competency.official_text = "Synthetic competency C3.2"
    context.competency.metadata_json = {"official_code": "C3.2"}
    db.flush()
    service = FrameworkStructureService(db, source_service=sources)
    specs = [
        spec.model_copy(
            update={
                "source_locator": "JSON pointer /mapping",
                **(
                    {"official_text": context.competency.official_text}
                    if spec.level == "competency"
                    else {}
                ),
            }
        )
        for spec in _specs(context)
    ]
    nodes = service.upsert_nodes(framework=context.framework, revision=revision, specs=specs)
    return context, service, nodes


def test_direct_link_retains_draft_status_and_registry_only_cannot_claim_direct(
    db: Session,
    tmp_path: Path,
) -> None:
    context, service, nodes = _direct_context(db, tmp_path)
    payload = _link_input(
        context,
        nodes["C3.2"].id,
        status="direct",
        inferred=False,
        source_locator="JSON pointer /mapping",
        evidence_text="Synthetic learning outcome maps to Synthetic competency C3.2.",
    )
    link = service.link_learning_outcome(payload)
    assert link.publication_status == "draft"
    assert link.status == "direct"
    assert service.link_learning_outcome(payload).id == link.id
    context.revision.ingestion_method = "manual"
    db.flush()
    with pytest.raises(FrameworkStructureError, match="retrieved source content"):
        service.link_learning_outcome(payload)


@pytest.mark.parametrize(
    "failure",
    [
        "cross_section",
        "fabricated_quote",
        "different_outcome",
        "tampered_bytes",
        "outcome_revision",
        "node_revision",
        "competency_revision",
        "wrong_node_locator",
    ],
)
def test_direct_mapping_requires_bounded_original_quote_and_target_provenance(
    db: Session,
    tmp_path: Path,
    failure: str,
) -> None:
    context, service, nodes = _direct_context(db, tmp_path)
    payload = _link_input(
        context,
        nodes["C3.2"].id,
        status="direct",
        inferred=False,
        source_locator="JSON pointer /mapping",
        evidence_text="Synthetic learning outcome maps to Synthetic competency C3.2.",
    )
    if failure == "cross_section":
        payload = payload.model_copy(update={"source_locator": "JSON pointer /unrelated"})
    elif failure == "fabricated_quote":
        payload = payload.model_copy(update={"evidence_text": "Invented direct relationship"})
    elif failure == "different_outcome":
        payload = payload.model_copy(
            update={
                "evidence_text": "Another outcome maps to C9.9.",
                "source_locator": "JSON pointer /unrelated",
            }
        )
    elif failure == "tampered_bytes":
        Path(service.source_service.storage.root / context.revision.storage_path).write_bytes(
            b"tampered"
        )
    elif failure == "wrong_node_locator":
        nodes["C3.2"].source_locator = "JSON pointer /unrelated"
    else:
        other = _context(db, "other")
        target = {
            "outcome_revision": context.outcome,
            "node_revision": nodes["C3.2"],
            "competency_revision": context.competency,
        }[failure]
        target.source_revision_id = other.revision.id
    db.flush()
    with pytest.raises(FrameworkStructureError):
        service.link_learning_outcome(payload)
    assert db.scalar(select(func.count()).select_from(LearningOutcomeCompetencyLink)) == 0


def test_inferred_link_commentary_is_not_required_to_be_source_quotation(db: Session) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    payload = _link_input(context, nodes["C3.2"].id, evidence_text="Derived pedagogical commentary")
    link = FrameworkStructureService(db).link_learning_outcome(payload)
    assert link.inferred and link.status == "partial"


@pytest.mark.parametrize(
    "field,value",
    [
        ("level", "unknown"),
        ("parent_level", "competency"),
        ("publication_status", "unmarked"),
        ("review_status", "unknown"),
    ],
)
def test_sqlite_rejects_invalid_stored_structure(db: Session, field: str, value: str) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    with pytest.raises(IntegrityError), db.begin_nested():
        setattr(nodes["mathematics"], field, value)
        db.flush()


def test_sqlite_rejects_cross_framework_parent_binding(db: Session) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    other = _context(db, "other")
    other_nodes = _tree(db, other)
    with pytest.raises(IntegrityError), db.begin_nested():
        nodes["mathematics"].parent_id = other_nodes["secondary"].id
        db.flush()


@pytest.mark.parametrize("dialect_name", ["sqlite", "postgresql"])
def test_framework_ddl_compiles_for_sqlite_and_postgresql(dialect_name: str) -> None:
    dialect_factory: Any = sqlite.dialect if dialect_name == "sqlite" else postgresql.dialect
    dialect = dialect_factory()
    for name in ("framework_structure_nodes", "learning_outcome_competency_links"):
        table = Base.metadata.tables[name]
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "source_revision_id" in ddl
        assert "publication_status" in ddl
        assert "review_status" in ddl
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect))


def test_framework_migration_roundtrip_and_metadata_match(tmp_path: Path) -> None:
    database = tmp_path / "framework-structure.db"
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database}"}

    def alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    alembic("upgrade", "head")
    engine = create_database_engine(f"sqlite:///{database}")
    assert {"framework_structure_nodes", "learning_outcome_competency_links"} <= set(
        inspect(engine).get_table_names()
    )
    with Session(engine) as session:
        context = _context(session)
        nodes = _tree(session, context)
        FrameworkStructureService(session).link_learning_outcome(
            _link_input(context, nodes["C3.2"].id)
        )
        session.commit()
    alembic("check")
    engine.dispose()
    alembic("downgrade", "20261003_0007")
    assert "framework_structure_nodes" not in inspect(engine).get_table_names()
    alembic("upgrade", "head")
    alembic("check")
    assert "framework_structure_nodes" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(select(func.count(EducationFramework.id))) == 1
    engine.dispose()


def test_framework_ingestion_does_not_commit_callers_transaction(db: Session) -> None:
    context = _context(db)
    db.commit()
    _tree(db, context)
    db.rollback()
    assert db.scalar(select(func.count(FrameworkStructureNode.id))) == 0


@pytest.mark.parametrize(
    "source_type,document_type",
    [
        ("sample_paper", None),
        ("marking_scheme", None),
        ("official_paper", None),
        ("answer_key", None),
        ("official_authority", "assessment_evidence"),
        ("official_authority", "sample_paper_index"),
        ("official_authority", "sample_question_paper"),
        ("official_authority", "marking_scheme"),
    ],
)
def test_assessment_snapshots_cannot_create_framework_or_outcome_mappings(
    db: Session, source_type: str, document_type: str | None
) -> None:
    context = _context(db)
    nodes = _tree(db, context)
    context.revision.metadata_json = {
        "source_snapshot": {
            "source_type": source_type,
            "metadata_json": {"document_type": document_type},
        }
    }
    # Editing the live registry cannot disguise the revision's assessment domain.
    context.revision.source.source_type = "official_authority"
    context.revision.source.metadata_json = {"document_type": "education_framework"}
    db.flush()
    service = FrameworkStructureService(db)
    with pytest.raises(FrameworkStructureError, match="assessment sources"):
        service.upsert_nodes(
            framework=context.framework, revision=context.revision, specs=_specs(context)
        )
    with pytest.raises(FrameworkStructureError, match="assessment sources"):
        service.link_learning_outcome(_link_input(context, nodes["C3.2"].id))
    assert db.scalar(select(func.count(LearningOutcomeCompetencyLink.id))) == 0


def test_direct_mapping_can_reference_independently_sourced_outcome_and_standard(
    db: Session,
    tmp_path: Path,
) -> None:
    import json

    from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
    from app.schemas.source_intelligence import SourceRegistrationInput

    context, service, nodes = _direct_context(db, tmp_path)
    sources = service.source_service
    revisions = {}
    for name, document_type in (
        ("outcome", "learning_outcomes"),
        ("mapping", "learning_standards"),
    ):
        source = sources.register_source(
            SourceRegistrationInput(
                source_type=SourceType.OFFICIAL_AUTHORITY,
                title=f"Synthetic {name}",
                url=f"https://synthetic.invalid/{name}.json",
                authority="Synthetic",
                country="Test",
                copyright_classification="synthetic_fixture",
                trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                metadata_json={"synthetic": True, "document_type": document_type},
            ),
            actor_id="test",
        )
        revision = sources.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            filename=f"{name}.json",
            content=json.dumps(
                {"mapping": "Synthetic learning outcome maps to Synthetic competency C3.2."}
            ).encode(),
            actor_id="test",
        )
        sources.extract_revision(revision.id, actor_id="test")
        sources.create_diff(revision.id, actor_id="test")
        assert sources.validate_revision(revision.id, actor_id="test").valid
        sources.approve_revision(revision.id, actor_id="test")
        revisions[name] = sources.activate_revision(revision.id, actor_id="test")
    context.outcome.source_revision_id = revisions["outcome"].id
    db.flush()
    payload = _link_input(
        context,
        nodes["C3.2"].id,
        status="direct",
        inferred=False,
        source_revision_id=revisions["mapping"].id,
        source_locator="JSON pointer /mapping",
        evidence_text="Synthetic learning outcome maps to Synthetic competency C3.2.",
    )
    link = service.link_learning_outcome(payload)
    assert link.status == "direct"
    assert (
        len(
            {
                link.source_revision_id,
                context.outcome.source_revision_id,
                context.competency.source_revision_id,
            }
        )
        == 3
    )


_SCOPED_IDENTITY = {
    "grade": "IX",
    "medium": "English",
    "subject": "Mathematics",
    "course_family": "General",
    "course_group": "MPC",
    "subject_language": "English",
    "language_role": "not_applicable",
    "book_part": "whole",
    "bilingual": "no",
}
_SCOPE_FIELDS = {
    "grade": "grades",
    "medium": "media",
    "subject": "subjects",
    "course_family": "course_families",
    "course_group": "course_groups",
    "subject_language": "subject_languages",
    "language_role": "language_roles",
    "book_part": "book_parts",
    "bilingual": "bilingual_states",
}


def _review_scope() -> dict[str, Any]:
    return {
        "pack_code": "synthetic-pack-one",
        "version_codes": ["2026-27"],
        "publication_status": "draft",
        "applicability_status": "verified",
        "applicability_locator": "JSON pointer /mapping",
        **{_SCOPE_FIELDS[key]: [value] for key, value in _SCOPED_IDENTITY.items()},
    }


def _scoped_mapping_context(
    db: Session, tmp_path: Path, own_scope: dict[str, Any] | None = None
) -> Any:
    context, service, nodes = _direct_context(db, tmp_path, scope=own_scope or _review_scope())
    context.version.metadata_json = {"scope_enforced": True}
    context.outcome.metadata_json = {"identity": dict(_SCOPED_IDENTITY)}
    context.competency.metadata_json = {
        **context.competency.metadata_json,
        "identity": dict(_SCOPED_IDENTITY),
    }
    db.flush()
    payload = _link_input(
        context,
        nodes["C3.2"].id,
        status="direct",
        inferred=False,
        source_locator="JSON pointer /mapping",
        evidence_text="Synthetic learning outcome maps to Synthetic competency C3.2.",
    )
    return context, service, nodes, payload


def _separate_scoped_mapping(
    service: FrameworkStructureService, scope: dict[str, Any], *, name: str = "mapping"
) -> SourceRevision:
    import json

    from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
    from app.schemas.source_intelligence import SourceRegistrationInput

    sources = service.source_service
    source = sources.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_AUTHORITY,
            title="Synthetic scoped mapping",
            url=f"https://synthetic.invalid/scoped-{name}.json",
            authority="Synthetic",
            country="Test",
            copyright_classification="synthetic_fixture",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "synthetic": True,
                "document_type": "learning_standards",
                "curriculum_scope": scope,
            },
        ),
        actor_id="test",
    )
    revision = sources.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="mapping.json",
        content=json.dumps(
            {"mapping": "Synthetic learning outcome maps to Synthetic competency C3.2."}
        ).encode(),
        actor_id="test",
    )
    sources.extract_revision(revision.id, actor_id="test")
    sources.create_diff(revision.id, actor_id="test")
    assert sources.validate_revision(revision.id, actor_id="test").valid
    sources.approve_revision(revision.id, actor_id="test")
    return sources.activate_revision(revision.id, actor_id="test")


def test_scoped_direct_link_validates_both_endpoints_and_separate_mapping_scope(
    db: Session, tmp_path: Path
) -> None:
    context, service, nodes, payload = _scoped_mapping_context(db, tmp_path)
    own_outcome = _separate_scoped_mapping(service, _review_scope(), name="outcome")
    context.outcome.source_revision_id = own_outcome.id
    db.flush()
    mapping = _separate_scoped_mapping(service, _review_scope())
    payload = payload.model_copy(update={"source_revision_id": UUID(mapping.id)})
    link = service.link_learning_outcome(payload)
    assert link.source_revision_id == mapping.id != context.outcome.source_revision_id
    assert len({mapping.id, own_outcome.id, context.competency.source_revision_id}) == 3
    assert service.link_learning_outcome(payload).id == link.id


@pytest.mark.parametrize("endpoint", ["outcome", "competency"])
@pytest.mark.parametrize("dimension", list(_SCOPED_IDENTITY))
def test_scoped_direct_link_rejects_missing_endpoint_dimension(
    db: Session, tmp_path: Path, endpoint: str, dimension: str
) -> None:
    context, service, nodes, payload = _scoped_mapping_context(db, tmp_path)
    entity = getattr(context, endpoint)
    entity.metadata_json = {
        **entity.metadata_json,
        "identity": {key: value for key, value in _SCOPED_IDENTITY.items() if key != dimension},
    }
    db.flush()
    with pytest.raises(FrameworkStructureError, match="nine identity"):
        service.link_learning_outcome(payload)


@pytest.mark.parametrize("dimension", list(_SCOPED_IDENTITY))
@pytest.mark.parametrize("fault", ["mapping_scope", "own_scope", "incompatible_endpoints"])
def test_scoped_direct_link_rejects_cross_scope_or_incompatible_endpoints(
    db: Session, tmp_path: Path, dimension: str, fault: str
) -> None:
    scope = _review_scope()
    if fault == "own_scope":
        scope[_SCOPE_FIELDS[dimension]] = ["other"]
    elif fault == "incompatible_endpoints":
        scope[_SCOPE_FIELDS[dimension]].append("other")
    context, service, nodes, payload = _scoped_mapping_context(db, tmp_path, scope)
    if fault == "mapping_scope":
        scope[_SCOPE_FIELDS[dimension]] = ["other"]
        mapping = _separate_scoped_mapping(service, scope)
        payload = payload.model_copy(update={"source_revision_id": UUID(mapping.id)})
    elif fault == "incompatible_endpoints":
        context.competency.metadata_json = {
            **context.competency.metadata_json,
            "identity": {**_SCOPED_IDENTITY, dimension: "other"},
        }
        db.flush()
    with pytest.raises(FrameworkStructureError):
        service.link_learning_outcome(payload)
    assert db.scalar(select(func.count()).select_from(LearningOutcomeCompetencyLink)) == 0
