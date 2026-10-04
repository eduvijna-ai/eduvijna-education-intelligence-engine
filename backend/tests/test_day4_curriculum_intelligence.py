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


def test_day4_verification_is_explicitly_synthetic_and_idempotent(db_session: Session) -> None:
    first = seed_day4_verification(db_session)
    second = seed_day4_verification(db_session)

    assert first["status"] == "synthetic_verification_passed"
    assert first["official_source_backed_acceptance"] is False
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
        select(Source).where(Source.url == "https://cbseacademic.nic.in/curriculum_2027.html")
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
            select(AssessmentEvidence).where(AssessmentEvidence.curriculum_version_id == version_id)
        )
    )
    assert len(evidence) == 1
    assert evidence[0].evidence_json["curriculum_membership_effect"] == "none"
    assert (
        db_session.scalar(
            select(func.count(CurriculumNode.id)).where(
                CurriculumNode.curriculum_version_id == version_id
            )
        )
        == node_count
    )


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
            select(AssessmentEvidence).where(AssessmentEvidence.curriculum_version_id == version_id)
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


class _ContentFetcher(SourceUrlFetcher):
    def __init__(self) -> None:
        self.calls = 0
        self.content = b"<html><body>Official test content version one.</body></html>"

    def fetch(self, url: str) -> Any:
        from app.source_intelligence.security import FetchedSource

        self.calls += 1
        return FetchedSource(self.content, url, "text/html", "official.html")


def test_fresh_official_fetch_extracts_before_lifecycle(
    db_session: Session, tmp_path: Path
) -> None:
    from app.source_intelligence.storage import LocalSourceStorage

    fetcher = _ContentFetcher()
    sources = SourceIntelligenceService(
        db_session, fetcher=fetcher, storage=LocalSourceStorage(tmp_path / "sources")
    )
    service = CurriculumIntelligenceService(db_session, source_service=sources)
    entry = load_source_manifest(SOURCE_MANIFEST)[0]
    revision = service.ensure_manifest_sources([entry], actor_id="test", fetch_content=True)[
        entry.key
    ]
    assert revision.status == "active"
    assert revision.extraction_status == "succeeded"
    assert revision.extracted_text
    assert not service.is_registry_only(revision)
    assert fetcher.calls == 1


def test_official_mode_refetches_registry_and_preserves_changed_content(
    db_session: Session,
    tmp_path: Path,
) -> None:
    from app.source_intelligence.storage import LocalSourceStorage

    fetcher = _ContentFetcher()
    sources = SourceIntelligenceService(
        db_session, fetcher=fetcher, storage=LocalSourceStorage(tmp_path / "sources")
    )
    service = CurriculumIntelligenceService(db_session, source_service=sources)
    entry = load_source_manifest(SOURCE_MANIFEST)[0]
    registry = service.ensure_manifest_sources([entry], actor_id="test")[entry.key]
    content = service.ensure_manifest_sources([entry], actor_id="test", fetch_content=True)[
        entry.key
    ]
    assert content.id != registry.id
    assert registry.status == "superseded"
    unchanged = service.ensure_manifest_sources([entry], actor_id="test", fetch_content=True)[
        entry.key
    ]
    assert unchanged.id == content.id
    fetcher.content = b"<html><body>Changed official content.</body></html>"
    with pytest.raises(CurriculumIntelligenceError, match="requires explicit review"):
        service.ensure_manifest_sources([entry], actor_id="test", fetch_content=True)
    db_session.refresh(content)
    assert content.status == "active"
    assert fetcher.calls == 3


def test_synthetic_provenance_never_claims_source_content(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    provenance = result["framework"]["provenance"]
    assert provenance["provenance_classification"] == "synthetic_registry_fixture"
    assert provenance["source_content_verified"] is False
    assert provenance["mapping_verified"] is False


def test_assessment_rejects_wrong_grade_in_same_version(db_session: Session) -> None:
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput

    result = seed_day4_verification(db_session)
    grade = db_session.scalar(select(CurriculumNode).where(CurriculumNode.code == "grade-ix"))
    subject = db_session.scalar(
        select(CurriculumNode).where(CurriculumNode.code == "grade-x-mathematics-standard")
    )
    assert grade is not None and subject is not None
    with pytest.raises(CurriculumIntelligenceError, match="supplied grade"):
        CurriculumIntelligenceService(db_session).add_assessment_evidence(
            AssessmentEvidenceInput(
                curriculum_version_id=result["curriculum"]["version_id"],
                grade_node_id=grade.id,
                subject_node_id=subject.id,
                source_revision_id=result["assessment_evidence"]["source_revision_id"],
                evidence_type="sample_paper",
            )
        )


def test_sqp_sources_cannot_create_syllabus_nodes(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    service = CurriculumIntelligenceService(db_session)
    version = db_session.get(CurriculumVersion, result["curriculum"]["version_id"])
    revision = db_session.get(
        app.models.SourceRevision, result["assessment_evidence"]["source_revision_id"]
    )
    assert version is not None and revision is not None
    with pytest.raises(CurriculumIntelligenceError, match="syllabus membership"):
        service.upsert_nodes(
            version=version,
            revision=revision,
            specs=[
                CurriculumNodeSpec(
                    node_type=CurriculumNodeType.GRADE_YEAR,
                    code="assessment-only-grade",
                    title="Forbidden",
                )
            ],
        )


def test_internal_query_returns_path_outcomes_and_competencies(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    path = CurriculumIntelligenceService(db_session).curriculum_path(
        result["founder_path"][-1]["id"]
    )
    assert len(path.node_ids) == 7
    assert str(path.learning_outcome_ids[0]) == result["learning_outcome"]["id"]
    assert str(path.competency_ids[0]) == result["competency"]["id"]
    assert len(path.alignment_ids) == 2
    assert path.source_revision_ids


def test_missing_parent_duplicate_codes_and_cycles_rejected(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    service = CurriculumIntelligenceService(db_session)
    version = db_session.get(CurriculumVersion, result["curriculum"]["version_id"])
    assert version is not None
    revision = db_session.get(app.models.SourceRevision, version.source_revision_id)
    assert revision is not None
    spec = CurriculumNodeSpec(
        node_type=CurriculumNodeType.GRADE_YEAR, code="test-grade", title="Test"
    )
    with pytest.raises(CurriculumIntelligenceError, match="unique node codes"):
        service.upsert_nodes(version=version, revision=revision, specs=[spec, spec])
    for code, parent in [("missing", "no-parent"), ("cycle", "cycle")]:
        with pytest.raises(CurriculumIntelligenceError, match="missing parents or a cycle"):
            service.upsert_nodes(
                version=version,
                revision=revision,
                specs=[
                    CurriculumNodeSpec(
                        node_type=CurriculumNodeType.TOPIC,
                        code=code,
                        title="Test",
                        parent_code=parent,
                    )
                ],
            )


def test_dns_failure_is_an_explicit_blocked_source(db_session: Session) -> None:
    import socket

    class DnsFailure(_BlockedFetcher):
        def fetch(self, url: str) -> Any:
            raise socket.gaierror("DNS unavailable")

    service = CurriculumIntelligenceService(
        db_session, source_service=SourceIntelligenceService(db_session, fetcher=DnsFailure())
    )
    entry = load_source_manifest(SOURCE_MANIFEST)[0]
    revision = service.ensure_manifest_sources([entry], actor_id="test", fetch_content=True)[
        entry.key
    ]
    assert service.is_registry_only(revision)
    assert revision.source.metadata_json["ingestion_status"] == "blocked_or_unavailable"


def test_registry_revision_cannot_back_direct_alignment(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    with pytest.raises(CurriculumIntelligenceError, match="retrieved source content"):
        CurriculumIntelligenceService(db_session).align(
            CurriculumAlignmentInput(
                curriculum_version_id=result["curriculum"]["version_id"],
                curriculum_node_id=result["founder_path"][-1]["id"],
                learning_outcome_id=result["learning_outcome"]["id"],
                relationship_type="directly_addresses",
                status="direct",
                source_revision_id=result["learning_outcome"]["source_revision_id"],
                source_locator="fixture",
                evidence_text="fixture",
            )
        )


def test_assessment_source_type_and_grade_applicability_are_enforced(db_session: Session) -> None:
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput

    result = seed_day4_verification(db_session)
    service = CurriculumIntelligenceService(db_session)
    grade = db_session.scalar(select(CurriculumNode).where(CurriculumNode.code == "grade-x"))
    subject = db_session.scalar(
        select(CurriculumNode).where(CurriculumNode.code == "grade-x-mathematics-standard")
    )
    assert grade is not None and subject is not None
    revisions = {source["key"]: source["source_revision_id"] for source in result["sources"]}
    for key, error in [
        ("ncfse-2023", "requires an assessment source"),
        ("cbse-class-xii-sqp-2026-27", "does not apply to supplied grade"),
    ]:
        with pytest.raises(CurriculumIntelligenceError, match=error):
            service.add_assessment_evidence(
                AssessmentEvidenceInput(
                    curriculum_version_id=result["curriculum"]["version_id"],
                    grade_node_id=grade.id,
                    subject_node_id=subject.id,
                    source_revision_id=revisions[key],
                    evidence_type="sample_paper",
                )
            )


def test_assessment_source_cannot_back_alignment(db_session: Session) -> None:
    result = seed_day4_verification(db_session)
    with pytest.raises(CurriculumIntelligenceError, match="assessment sources"):
        CurriculumIntelligenceService(db_session).align(
            CurriculumAlignmentInput(
                curriculum_version_id=result["curriculum"]["version_id"],
                curriculum_node_id=result["founder_path"][-1]["id"],
                learning_outcome_id=result["learning_outcome"]["id"],
                source_revision_id=result["assessment_evidence"]["source_revision_id"],
                relationship_type="addresses",
                status="partial",
                inferred=True,
            )
        )


@pytest.mark.parametrize("action", ["node", "alignment", "assessment"])
def test_superseded_revisions_are_read_only(db_session: Session, action: str) -> None:
    from app.schemas.curriculum_intelligence import AssessmentEvidenceInput

    result = seed_day4_verification(db_session)
    service = CurriculumIntelligenceService(db_session)
    revision_id = (
        result["assessment_evidence"]["source_revision_id"]
        if action == "assessment"
        else (result["learning_outcome"]["source_revision_id"])
    )
    revision = db_session.get(app.models.SourceRevision, revision_id)
    version = db_session.get(CurriculumVersion, result["curriculum"]["version_id"])
    assert revision is not None and version is not None
    revision.status = "superseded"
    revision.active_slot = None
    db_session.flush()
    with pytest.raises(CurriculumIntelligenceError, match="active SourceRevision"):
        if action == "node":
            service.upsert_nodes(
                version=version,
                revision=revision,
                specs=[
                    CurriculumNodeSpec(
                        node_type=CurriculumNodeType.GRADE_YEAR, code="new-old", title="Old"
                    )
                ],
            )
        elif action == "alignment":
            service.align(
                CurriculumAlignmentInput(
                    curriculum_version_id=version.id,
                    curriculum_node_id=result["founder_path"][-1]["id"],
                    learning_outcome_id=result["learning_outcome"]["id"],
                    source_revision_id=revision.id,
                    relationship_type="new-old",
                    status="partial",
                )
            )
        else:
            service.add_assessment_evidence(
                AssessmentEvidenceInput(
                    curriculum_version_id=version.id,
                    source_revision_id=revision.id,
                    evidence_type="new-old",
                )
            )
    entity_type = "assessment_evidence" if action == "assessment" else "learning_outcome"
    entity_id = (
        result["assessment_evidence"]["id"]
        if action == "assessment"
        else result["learning_outcome"]["id"]
    )
    assert (
        service.provenance(entity_type=entity_type, entity_id=entity_id)["revision_status"]
        == "superseded"
    )


def test_competency_alignment_cannot_cross_frameworks(db_session: Session) -> None:
    from app.schemas.curriculum_intelligence import CompetencySpec

    result = seed_day4_verification(db_session)
    service = CurriculumIntelligenceService(db_session)
    revision = db_session.get(app.models.SourceRevision, result["competency"]["source_revision_id"])
    assert revision is not None
    other = service.ensure_framework(
        code="other-framework",
        name="Other",
        country="India",
        authority="Synthetic test",
        version_code="test",
        revision=revision,
    )
    competency = service.upsert_competencies(
        framework=other,
        revision=revision,
        specs=[CompetencySpec(code="other-competency", name="Other")],
    )["other-competency"]
    with pytest.raises(CurriculumIntelligenceError, match="curriculum framework"):
        service.align(
            CurriculumAlignmentInput(
                curriculum_version_id=result["curriculum"]["version_id"],
                curriculum_node_id=result["founder_path"][-1]["id"],
                competency_id=competency.id,
                source_revision_id=revision.id,
                relationship_type="addresses",
                status="partial",
            )
        )
