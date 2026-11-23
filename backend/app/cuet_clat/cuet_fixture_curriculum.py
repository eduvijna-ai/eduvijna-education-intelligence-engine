"""D13 synthetic curriculum fixture — non-official teacher content with real byte receipts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import (
    Competency,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
    LearningOutcome,
)
from app.models.enums import CurriculumNodeType, CurriculumStatus, SourceType
from app.models.source import Source, SourceRevision

D13_CURRICULUM_VERSION_CODE = "d13-synthetic-2026"
D13_FRAMEWORK_CODE = "d13-cuet-math-fixture"
D13_PACK_CODE = "d13-cuet-math-fixture-pack"
D13_LO_CODE = "LO-CUET-MATH-01"

# Deterministic tiny original text — not official NTA/Consortium material.
D13_FIXTURE_SOURCE_BYTES = (
    b"D13 synthetic CUET mathematics fixture curriculum note. "
    b"For automated Day6 validation tests only; not an official syllabus."
)


def _fixture_source_checksum() -> str:
    return hashlib.sha256(D13_FIXTURE_SOURCE_BYTES).hexdigest()


def _load_existing_context(session: Session) -> dict[str, str] | None:
    version = session.scalar(
        select(CurriculumVersion).where(
            CurriculumVersion.version_code == D13_CURRICULUM_VERSION_CODE
        )
    )
    if version is None:
        return None
    lo = session.scalar(
        select(LearningOutcome).where(
            LearningOutcome.curriculum_version_id == version.id,
            LearningOutcome.code == D13_LO_CODE,
        )
    )
    if lo is None:
        return None
    return {
        "curriculum_version_id": str(version.id),
        "learning_outcome_id": str(lo.id),
        "competency_code": "application",
        "subject_code": "mathematics",
        "source_revision_id": str(lo.source_revision_id or ""),
    }


def seed_cuet_math_fixture_curriculum(session: Session) -> dict[str, str]:
    """Idempotent non-official curriculum seed for Day6 validation of D13 synthetic items."""

    existing = _load_existing_context(session)
    if existing is not None:
        return existing

    checksum = _fixture_source_checksum()
    source = Source(
        source_type=SourceType.SAMPLE_PAPER.value,
        title="D13 sample-paper math fixture (synthetic, non-official)",
        metadata_json={
            "d13_synthetic_fixture": True,
            "not_official_cuet_source": True,
            "not_curator_approved": True,
            "fixture_bytes_sha256": checksum,
            "fixture_byte_size": len(D13_FIXTURE_SOURCE_BYTES),
        },
    )
    framework = EducationFramework(
        code=D13_FRAMEWORK_CODE,
        name="D13 CUET Math Fixture",
        country="IN",
    )
    pack = CurriculumPack(
        code=D13_PACK_CODE,
        name="D13 CUET Mathematics Fixture Pack",
        country="IN",
        framework=framework,
    )
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code=D13_CURRICULUM_VERSION_CODE,
        status=CurriculumStatus.ACTIVE.value,
        academic_year="2026",
        metadata_json={
            "d13_synthetic_fixture": True,
            "not_official_syllabus_replica": True,
        },
    )
    version.sources.append(source)
    session.add_all([source, framework, pack, version])
    session.flush()

    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum=checksum,
        source_snapshot_checksum=checksum,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=len(D13_FIXTURE_SOURCE_BYTES),
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum=checksum,
        metadata_json={
            "d13_synthetic_fixture": True,
            "fixture_scope_only": True,
            "not_nta_official_active_slot": True,
            "fixture_sample_paper_only": True,
        },
    )
    session.add(revision)
    session.flush()

    grade = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="ug-year-1",
        title="UG year 1",
        metadata_json={"authoritative_age_min": 17, "authoritative_age_max": 20},
    )
    medium = CurriculumNode(
        curriculum_version=version,
        parent=grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="english",
        title="English medium",
    )
    subject = CurriculumNode(
        curriculum_version=version,
        parent=medium,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    lo = LearningOutcome(
        curriculum_version=version,
        code=D13_LO_CODE,
        text="Synthetic LO: perform basic numeric operations (fixture only).",
        active=True,
        source_revision_id=revision.id,
    )
    lo.nodes.append(subject)
    comp = Competency(
        code="application",
        name="Application",
        framework=framework,
        active=True,
        source_revision_id=revision.id,
    )
    comp.nodes.append(subject)
    session.add_all([grade, medium, subject, lo, comp])
    session.flush()
    return {
        "curriculum_version_id": str(version.id),
        "learning_outcome_id": str(lo.id),
        "competency_code": "application",
        "subject_code": "mathematics",
        "source_revision_id": str(revision.id),
    }