from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ca_imat_eapcet.constants import (
    CA_AUTHORITY,
    CA_FOUNDATION_PACK_CODE,
    CA_MARKS_PER_PAPER,
    CA_PAPER_CODES,
    EAPCET_AUTHORITY,
    EAPCET_PACK_CODE,
    EAPCET_TOTAL_MINUTES,
    EAPCET_TOTAL_QUESTIONS,
    IMAT_AUTHORITY,
    IMAT_PACK_CODE,
    IMAT_TOTAL_MINUTES,
    IMAT_TOTAL_QUESTIONS,
    VERSION_CA_SYNTHETIC_DEMO,
    VERSION_EAPCET_SYNTHETIC,
    VERSION_IMAT_2026_REF,
)
from app.models.examination import ExamPack, ExamSection, ExamVersion


def ensure_day14_exam_packs(session: Session) -> tuple[ExamPack, ExamPack, ExamPack]:
    """D14-05/06/16/21: bootstrap packs via generic ExamPack model (no engine branches)."""

    packs: list[ExamPack] = []
    for code, name, authority, meta in (
        (
            CA_FOUNDATION_PACK_CODE,
            "CA Foundation",
            CA_AUTHORITY,
            {"examination_family": "ca_foundation", "papers": list(CA_PAPER_CODES)},
        ),
        (
            IMAT_PACK_CODE,
            "IMAT",
            IMAT_AUTHORITY,
            {"examination_family": "imat", "question_count": IMAT_TOTAL_QUESTIONS, "country": "IN"},
        ),
        (
            EAPCET_PACK_CODE,
            "TG EAPCET",
            EAPCET_AUTHORITY,
            {"examination_family": "tg_eapcet", "streams": ["engineering", "agriculture_pharmacy"]},
        ),
    ):
        pack = session.scalar(select(ExamPack).where(ExamPack.code == code))
        if pack is None:
            country = "IN"
            pack = ExamPack(
                code=code,
                name=name,
                authority=authority,
                country=country,
                metadata_json=meta,
            )
            session.add(pack)
            session.flush()
        packs.append(pack)
    return packs[0], packs[1], packs[2]


def ensure_synthetic_demo_versions(
    session: Session,
) -> tuple[ExamVersion, ExamVersion, ExamVersion]:
    ca_pack, imat_pack, eapcet_pack = ensure_day14_exam_packs(session)

    def _version(
        pack: ExamPack,
        ver_code: str,
        year: str,
        minutes: int,
        extra: dict[str, object],
    ) -> ExamVersion:
        ver = session.scalar(
            select(ExamVersion).where(
                ExamVersion.exam_pack_id == pack.id,
                ExamVersion.version_code == ver_code,
            )
        )
        if ver is None:
            ver = ExamVersion(
                exam_pack_id=pack.id,
                version_code=ver_code,
                academic_year=year,
                duration_minutes=minutes,
                metadata_json=extra,
            )
            session.add(ver)
            session.flush()
        return ver

    ca_ver = _version(
        ca_pack,
        VERSION_CA_SYNTHETIC_DEMO,
        "2027",
        180,
        {"trust_mode": "synthetic_fixture", "marks_per_paper": CA_MARKS_PER_PAPER},
    )
    imat_ver = _version(
        imat_pack,
        VERSION_IMAT_2026_REF,
        "2026",
        IMAT_TOTAL_MINUTES,
        {"trust_mode": "synthetic_fixture", "questions": IMAT_TOTAL_QUESTIONS},
    )
    eapcet_ver = _version(
        eapcet_pack,
        VERSION_EAPCET_SYNTHETIC,
        "2026",
        EAPCET_TOTAL_MINUTES,
        {"trust_mode": "synthetic_fixture", "questions": EAPCET_TOTAL_QUESTIONS},
    )

    ca_sections = session.scalars(
        select(ExamSection).where(ExamSection.exam_version_id == ca_ver.id)
    ).first()
    if not ca_sections:
        for seq, paper in enumerate(CA_PAPER_CODES, start=1):
            session.add(
                ExamSection(
                    exam_version_id=ca_ver.id,
                    code=paper,
                    title=paper.replace("_", " ").title(),
                    sequence=seq,
                    duration_minutes=45,
                    metadata_json={"marks": CA_MARKS_PER_PAPER},
                )
            )

    return ca_ver, imat_ver, eapcet_ver