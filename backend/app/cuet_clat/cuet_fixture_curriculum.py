"""Minimal curriculum seed for Day6 validation of D13 synthetic CUET math items."""

from __future__ import annotations

from datetime import UTC, datetime

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


def seed_cuet_math_fixture_curriculum(session: Session) -> dict[str, str]:
    """Synthetic curriculum references only — not official CUET syllabus text."""

    source = Source(
        source_type=SourceType.OFFICIAL_SYLLABUS.value,
        title="Synthetic CUET math curriculum reference (non-copyright fixture)",
        metadata_json={"d13_synthetic_fixture": True},
    )
    framework = EducationFramework(
        code="cuet-math-fixture",
        name="CUET Math Fixture",
        country="IN",
    )
    pack = CurriculumPack(
        code="cuet-math-fixture-pack",
        name="CUET Mathematics Fixture Pack",
        country="IN",
        framework=framework,
    )
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="d13-synthetic-2026",
        status=CurriculumStatus.ACTIVE.value,
        academic_year="2026",
        metadata_json={"d13_synthetic_fixture": True},
    )
    version.sources.append(source)
    session.add_all([source, framework, pack, version])
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="e" * 64,
        source_snapshot_checksum="f" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="e" * 64,
        metadata_json={"d13_synthetic_fixture": True},
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
        code="LO-CUET-MATH-01",
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
    session.add_all([revision, grade, medium, subject, lo, comp])
    session.flush()
    return {
        "curriculum_version_id": str(version.id),
        "learning_outcome_id": str(lo.id),
        "competency_code": "application",
        "subject_code": "mathematics",
    }