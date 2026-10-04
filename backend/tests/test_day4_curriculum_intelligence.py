from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.service import (
    CurriculumIntelligenceError,
    CurriculumIntelligenceService,
    load_source_manifest,
)
from app.day4_verify import SOURCE_MANIFEST, seed_day4_verification
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.curriculum import CurriculumNode, CurriculumVersion
from app.models.curriculum_intelligence import AssessmentEvidence, CurriculumAlignment
from app.models.enums import CurriculumNodeType, SourceIngestionMethod, SourceRevisionStatus
from app.models.source import Source
from app.schemas.curriculum_intelligence import (
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
)
from app.schemas.source_intelligence import ManualSourceRevisionInput
from app.source_intelligence.security import SourceFetchError, SourceUrlFetcher
from app.source_intelligence.service import SourceIntelligenceService


@pytest.fixture
def db_session() -> Session:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
        create_database_engine.cache_clear()


def test_day4_verification_is_source_backed_and_idempotent(db_session: Session) -> None:
    first = seed_day4_verification(db_session)
    second = seed_day4_verification(db_session)

    assert first["status"] == "verification_passed"
    assert first["framework"]["id"] == second["framework"]["id"]
    assert first["curriculum"]["version_id"] == second["curriculum"]["version_id"]
    assert first["curriculum"]["counts"] == second["curriculum"]["counts"]

    path_types = [item["type"] for item in first["founder_path"]]
    assert path_types == [
        "grade_year",
        "medium",
        "subject",
        "unit",
        "chapter",
        "topic",
        "concept",
    ]
    assert all(item["source_revision_id"] for item in first["founder_path"])
    assert first["learning_outcome"]["source_revision_id"]
    assert first["competency"]["source_revision_id"]
    assert first["assessment_evidence"]["curriculum_membership_effect"] == "none"
    assert len(first["sources"]) >= 7
    assert all(source["checksum"] for source in first["sources"])


def test_alignment_status_never_promotes_inference_to_direct() -> None:
    with pytest.raises(ValidationError):
        CurriculumAlignmentInput(
            curriculum_version_id="18ed948d-4ba5-4f4d-a97d-cba9fb3de3a7",
            curriculum_node_id="271c0b7d-21c5-44e9-8c10-69067dfcf29c",
            competency_id="00a204d6-d25d-4f38-a9aa-a6c3d6e81352",
            relationship_type="develops",
            status="direct",
            confidence=0.8,
            inferred=True,
            source_revision_id="60db499d-ac43-4d76-9f08-7d79a49bdff5",
        )


def test_invalid_parent_type_is_rejected(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    version = db_session.get(CurriculumVersion, result["curriculum"]["version_id"])
    assert version is not None
    service = CurriculumIntelligenceService(db_session)

    subject = db_session.scalar(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id,
            CurriculumNode.code == "grade-ix-mathematics",
        )
    )
    assert subject is not None
    revision = subject.source_revision_id
    assert revision is not None
    source_revision = db_session.get(app.models.SourceRevision, revision)
    assert source_revision is not None

    with pytest.raises(CurriculumIntelligenceError, match="invalid hierarchy"):
        service.upsert_nodes(
            version=version,
            revision=source_revision,
            specs=[
                CurriculumNodeSpec(
                    node_type=CurriculumNodeType.TOPIC,
                    code="invalid-topic-under-subject",
                    title="Invalid Topic",
                    parent_code=subject.code,
                )
            ],
        )


def test_changed_source_revision_requires_explicit_curriculum_review(
    db_session: Session,
) -> None:
    result = seed_day4_verification(db_session)
    version = db_session.get(CurriculumVersion, result["curriculum"]["version_id"])
    assert version is not None
    service = CurriculumIntelligenceService(db_session)

    source = db_session.scalar(
        select(Source).where(
            Source.url == "https://cbseacademic.nic.in/curriculum_2027.html"
        )
    )
    assert source is not None
    new_revision = service.source_service.ingest_manual(
        source.id,
        ManualSourceRevisionInput(
            metadata={
                "candidate_version": "2026-27",
                "change_marker": "test-source-change",
            },
            note="Day-4 source-change regression",
        ),
        actor_id="test-reviewer",
    )
    service.source_service.create_diff(new_revision.id, actor_id="test-reviewer")
    validation = service.source_service.validate_revision(
        new_revision.id,
        actor_id="test-reviewer",
    )
    assert validation.valid
    service.source_service.approve_revision(
        new_revision.id,
        actor_id="test-reviewer",
    )
    new_revision = service.source_service.activate_revision(
        new_revision.id,
        actor_id="test-reviewer",
    )

    with pytest.raises(CurriculumIntelligenceError, match="cannot silently rebind"):
        service.ensure_version(
            pack=version.curriculum_pack,
            version_code=version.version_code,
            academic_year=version.academic_year,
            revision=new_revision,
            source_locator="changed official source",
        )

    db_session.refresh(version)
    assert version.source_revision_id != new_revision.id


def test_assessment_evidence_is_separate_from_curriculum_membership(
    db_session: Session,
) -> None:
    result = seed_day4_verification(db_session)
    version_id = result["curriculum"]["version_id"]
    node_count = db_session.scalar(
        select(func.count(CurriculumNode.id)).where(
            CurriculumNode.curriculum_version_id == version_id
        )
    )
    evidence = list(
        db_session.scalars(
            select(AssessmentEvidence).where(
                AssessmentEvidence.curriculum_version_id == version_id
            )
        )
    )
    assert len(evidence) == 1
    assert evidence[0].evidence_json["curriculum_membership_effect"] == "none"
    assert db_session.scalar(
        select(func.count(CurriculumNode.id)).where(
            CurriculumNode.curriculum_version_id == version_id
        )
    ) == node_count


class _BlockedFetcher(SourceUrlFetcher):
    def __init__(self) -> None:
        pass

    def fetch(self, url: str) -> Any:
        raise SourceFetchError(f"blocked for test: {url}")


def test_blocked_official_source_records_manual_fallback(db_session: Session) -> None:
    source_service = SourceIntelligenceService(
        db_session,
        fetcher=_BlockedFetcher(),
    )
    service = CurriculumIntelligenceService(
        db_session,
        source_service=source_service,
    )
    entry = load_source_manifest(Path(SOURCE_MANIFEST))[0]
    revisions = service.ensure_manifest_sources(
        [entry],
        actor_id="test",
        fetch_content=True,
        fallback_on_fetch_error=True,
    )
    revision = revisions[entry.key]
    source = db_session.get(Source, revision.source_id)
    assert source is not None
    assert source.metadata_json["ingestion_status"] == "blocked_or_unavailable"
    assert source.metadata_json["fallback"] == "manual_registry_only"
    assert revision.ingestion_method == SourceIngestionMethod.MANUAL.value
    assert revision.status == SourceRevisionStatus.ACTIVE.value
    manual_metadata = revision.metadata_json["manual_metadata"]
    assert manual_metadata["registry_only"] is True
    assert "blocked_reason" in manual_metadata


def test_alignment_and_assessment_records_have_exact_revision_provenance(
    db_session: Session,
) -> None:
    result = seed_day4_verification(db_session)
    version_id = result["curriculum"]["version_id"]
    alignments = list(
        db_session.scalars(
            select(CurriculumAlignment).where(
                CurriculumAlignment.curriculum_version_id == version_id
            )
        )
    )
    evidence = list(
        db_session.scalars(
            select(AssessmentEvidence).where(
                AssessmentEvidence.curriculum_version_id == version_id
            )
        )
    )
    assert alignments
    assert evidence
    assert all(item.source_revision_id for item in alignments)
    assert all(item.source_revision_id for item in evidence)
    assert {item.status for item in alignments} <= {
        "direct",
        "partial",
        "unresolved",
        "review_required",
    }
    assert all(item.inferred for item in alignments if item.status != "direct")
