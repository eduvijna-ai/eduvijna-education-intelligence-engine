from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.constants import (
    CLAT_AUTHORITY,
    CLAT_PACK_CODE,
    CLAT_TOTAL_MINUTES,
    CLAT_TOTAL_QUESTIONS,
    CUET_AUTHORITY,
    CUET_MINUTES_PER_TEST,
    CUET_PACK_CODE,
    CUET_QUESTIONS_PER_TEST,
    VERSION_CLAT_2027,
    VERSION_SYNTHETIC_DEMO,
)
from app.models.examination import ExamPack, ExamSection, ExamVersion


def ensure_cuet_clat_exam_packs(session: Session) -> tuple[ExamPack, ExamPack]:
    """D13-07/15: bootstrap CUET and CLAT packs without hard-coded generic branches."""

    cuet = session.scalar(select(ExamPack).where(ExamPack.code == CUET_PACK_CODE))
    if cuet is None:
        cuet = ExamPack(
            code=CUET_PACK_CODE,
            name="CUET UG",
            authority=CUET_AUTHORITY,
            country="IN",
            metadata_json={
                "examination_family": "cuet_ug",
                "day_isolation": 13,
                "questions_per_test": CUET_QUESTIONS_PER_TEST,
            },
        )
        session.add(cuet)
        session.flush()

    clat = session.scalar(select(ExamPack).where(ExamPack.code == CLAT_PACK_CODE))
    if clat is None:
        clat = ExamPack(
            code=CLAT_PACK_CODE,
            name="CLAT UG",
            authority=CLAT_AUTHORITY,
            country="IN",
            metadata_json={
                "examination_family": "clat_ug",
                "day_isolation": 13,
                "total_questions": CLAT_TOTAL_QUESTIONS,
            },
        )
        session.add(clat)
        session.flush()

    return cuet, clat


def ensure_synthetic_demo_versions(session: Session) -> tuple[ExamVersion, ExamVersion]:
    cuet_pack, clat_pack = ensure_cuet_clat_exam_packs(session)

    cuet_ver = session.scalar(
        select(ExamVersion).where(
            ExamVersion.exam_pack_id == cuet_pack.id,
            ExamVersion.version_code == VERSION_SYNTHETIC_DEMO,
        )
    )
    if cuet_ver is None:
        cuet_ver = ExamVersion(
            exam_pack_id=cuet_pack.id,
            version_code=VERSION_SYNTHETIC_DEMO,
            academic_year="2026",
            duration_minutes=CUET_MINUTES_PER_TEST,
            metadata_json={"trust_mode": "synthetic_fixture"},
        )
        session.add(cuet_ver)
        session.flush()
        session.add(
            ExamSection(
                exam_version_id=cuet_ver.id,
                code="single_test",
                title="Single domain test",
                sequence=1,
                duration_minutes=CUET_MINUTES_PER_TEST,
                metadata_json={"question_count": CUET_QUESTIONS_PER_TEST},
            )
        )

    clat_ver = session.scalar(
        select(ExamVersion).where(
            ExamVersion.exam_pack_id == clat_pack.id,
            ExamVersion.version_code == VERSION_CLAT_2027,
        )
    )
    if clat_ver is None:
        clat_ver = ExamVersion(
            exam_pack_id=clat_pack.id,
            version_code=VERSION_CLAT_2027,
            academic_year="2027",
            duration_minutes=CLAT_TOTAL_MINUTES,
            metadata_json={"source_attested": False},
        )
        session.add(clat_ver)
        session.flush()

    return cuet_ver, clat_ver