from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.authority import version_code_for_profile
from app.jee_advanced.constants import (
    JEE_ADVANCED_AUTHORITY,
    JEE_ADVANCED_PACK_CODE,
    OFFICIAL_SUBJECTS,
    PAPER_1_CODE,
    PAPER_2_CODE,
    REFERENCE_PAPER_DURATION_MINUTES,
)
from app.jee_advanced.enums import AdvancedProfileKind, JeeAdvancedSourceTrustMode
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models.enums import ExamStatus
from app.models.examination import ExamPack, ExamSection, ExamVersion


def ensure_jee_advanced_exam_pack(session: Session) -> ExamPack:
    """D12-06: isolated JEE Advanced pack; does not mutate other examination packs."""

    existing = session.scalar(select(ExamPack).where(ExamPack.code == JEE_ADVANCED_PACK_CODE))
    if existing is not None:
        return existing
    pack = ExamPack(
        code=JEE_ADVANCED_PACK_CODE,
        name="JEE Advanced",
        authority=JEE_ADVANCED_AUTHORITY,
        country="IN",
        metadata_json={"examination_family": "jee_advanced", "day12_isolated": True},
    )
    session.add(pack)
    session.flush()
    return pack


def ensure_exam_version(
    session: Session,
    *,
    pack: ExamPack,
    profile_kind: AdvancedProfileKind,
    academic_year: str,
) -> ExamVersion:
    version_code = version_code_for_profile(profile_kind)
    existing = session.scalar(
        select(ExamVersion).where(
            ExamVersion.exam_pack_id == pack.id,
            ExamVersion.version_code == version_code,
        )
    )
    if existing is not None:
        return existing

    trust_by_profile = {
        AdvancedProfileKind.SYNTHETIC_DEMO: JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
        AdvancedProfileKind.REFERENCE_2026: JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        AdvancedProfileKind.CANDIDATE_2027: JeeAdvancedSourceTrustMode.OFFICIAL_2027_NOT_VERIFIED,
    }
    trust_mode = trust_by_profile[profile_kind].value

    status = ExamStatus.DRAFT.value
    if profile_kind is AdvancedProfileKind.SYNTHETIC_DEMO:
        status = ExamStatus.ACTIVE.value

    version = ExamVersion(
        exam_pack=pack,
        version_code=version_code,
        academic_year=academic_year,
        duration_minutes=REFERENCE_PAPER_DURATION_MINUTES,
        total_marks=None,
        status=status,
        metadata_json={
            "profile_kind": profile_kind.value,
            "trust_mode": trust_mode,
            "reference_sources_approved": reference_evidence_ready(),
            "blueprint_counts_pinned": False,
            "note": "Per-paper question counts require approved paper-specific instructions.",
        },
    )
    session.add(version)
    session.flush()
    _ensure_two_paper_hierarchy(session, version)
    return version


def _ensure_two_paper_hierarchy(session: Session, version: ExamVersion) -> None:
    """D12-07: version → Paper1/Paper2 → PCM subjects (no single-paper official PASS)."""

    if version.sections:
        return

    for paper_seq, paper_code in enumerate((PAPER_1_CODE, PAPER_2_CODE), start=1):
        paper = ExamSection(
            exam_version=version,
            code=paper_code,
            title=f"Paper {paper_seq}",
            sequence=paper_seq,
            duration_minutes=REFERENCE_PAPER_DURATION_MINUTES,
            metadata_json={
                "compulsory": True,
                "trust_mode": version.metadata_json.get("trust_mode"),
            },
        )
        session.add(paper)
        session.flush()
        for subject_seq, subject_code in enumerate(OFFICIAL_SUBJECTS, start=1):
            session.add(
                ExamSection(
                    exam_version=version,
                    parent=paper,
                    parent_section_id=paper.id,
                    parent_exam_version_id=version.id,
                    code=subject_code,
                    title=subject_code.replace("_", " ").title(),
                    sequence=subject_seq,
                    subject_code=subject_code,
                    metadata_json={"jee_advanced_official_subject": True},
                )
            )
    session.flush()


def describe_exam_profile(version: ExamVersion) -> dict[str, Any]:
    papers = [s for s in version.sections if s.parent_section_id is None]
    return {
        "version_code": version.version_code,
        "academic_year": version.academic_year,
        "paper_count": len(papers),
        "paper_codes": [p.code for p in sorted(papers, key=lambda s: s.sequence)],
        "duration_minutes_per_paper": REFERENCE_PAPER_DURATION_MINUTES,
        "metadata_json": version.metadata_json,
    }
