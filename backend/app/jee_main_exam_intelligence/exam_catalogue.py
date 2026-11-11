from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_MARKS_CORRECT,
    CANDIDATE_MARKS_INCORRECT,
    CANDIDATE_MARKS_UNATTEMPTED,
    CANDIDATE_PAPER1_DURATION_MINUTES,
    CANDIDATE_PAPER1_TOTAL_MARKS,
    CANDIDATE_PAPER1_TOTAL_QUESTIONS,
    CANDIDATE_SECTION_A_MCQ,
    CANDIDATE_SECTION_B_NUMERICAL,
    CANDIDATE_SUBJECT_QUESTION_COUNT,
    JEE_MAIN_AUTHORITY,
    JEE_MAIN_COUNTRY,
    JEE_MAIN_EXAM_PACK_CODE,
    JEE_MAIN_VERSION_2026,
    JEE_MAIN_VERSION_2027,
)
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSectionCode,
    JeeMainSubjectCode,
)
from app.models.enums import ExamStatus
from app.models.examination import ExamBlueprintRule, ExamPack, ExamSection, ExamVersion


def _rule_type(section: JeeMainSectionCode, qtype: JeeMainQuestionTypeQuota) -> str:
    return f"{section.value}_{qtype.value}"


def ensure_jee_main_exam_catalogue(session: Session) -> dict[str, Any]:
    pack = session.scalar(select(ExamPack).where(ExamPack.code == JEE_MAIN_EXAM_PACK_CODE))
    if pack is None:
        pack = ExamPack(
            code=JEE_MAIN_EXAM_PACK_CODE,
            name="JEE Main",
            authority=JEE_MAIN_AUTHORITY,
            country=JEE_MAIN_COUNTRY,
            metadata_json={"paper_tracks": ["paper-1-be-btech"]},
        )
        session.add(pack)
        session.flush()

    ctx: dict[str, Any] = {"exam_pack_id": pack.id, "versions": {}}
    for version_code, academic_year, official_verified in (
        (JEE_MAIN_VERSION_2026, "2025-26", False),
        (JEE_MAIN_VERSION_2027, "2026-27", False),
    ):
        version = session.scalar(
            select(ExamVersion).where(
                ExamVersion.exam_pack_id == pack.id,
                ExamVersion.version_code == version_code,
            )
        )
        if version is None:
            version = ExamVersion(
                exam_pack_id=pack.id,
                version_code=version_code,
                academic_year=academic_year,
                effective_from=(
                    date(2025, 1, 1)
                    if version_code == JEE_MAIN_VERSION_2026
                    else date(2026, 1, 1)
                ),
                duration_minutes=CANDIDATE_PAPER1_DURATION_MINUTES,
                total_marks=CANDIDATE_PAPER1_TOTAL_MARKS,
                status=ExamStatus.DRAFT.value,
                metadata_json={
                    "official_pattern_verified": official_verified,
                    "nta_exam_version_code": version_code,
                    "candidate_total_questions": CANDIDATE_PAPER1_TOTAL_QUESTIONS,
                    "marking": {
                        "correct": CANDIDATE_MARKS_CORRECT,
                        "incorrect": CANDIDATE_MARKS_INCORRECT,
                        "unattempted": CANDIDATE_MARKS_UNATTEMPTED,
                    },
                    "pattern_activation_note": (
                        "Candidate pattern stored as typed blueprint data; "
                        "hard official replica requires approved NTA bulletin."
                    ),
                },
            )
            session.add(version)
            session.flush()
        _ensure_paper1_sections_and_rules(session, version)
        ctx["versions"][version_code] = version.id
    return ctx


def _ensure_paper1_sections_and_rules(session: Session, version: ExamVersion) -> None:
    root = session.scalar(
        select(ExamSection).where(
            ExamSection.exam_version_id == version.id,
            ExamSection.parent_section_id.is_(None),
            ExamSection.code == "paper-1",
        )
    )
    if root is None:
        root = ExamSection(
            exam_version_id=version.id,
            code="paper-1",
            title="Paper 1 (B.E./B.Tech.)",
            sequence=0,
            metadata_json={"source_locator_pending": True},
        )
        session.add(root)
        session.flush()

    for subj_index, subject in enumerate(JeeMainSubjectCode, start=1):
        subject_section = session.scalar(
            select(ExamSection).where(
                ExamSection.exam_version_id == version.id,
                ExamSection.parent_section_id == root.id,
                ExamSection.code == subject.value,
            )
        )
        if subject_section is None:
            subject_section = ExamSection(
                exam_version_id=version.id,
                parent_section_id=root.id,
                parent_exam_version_id=version.id,
                code=subject.value,
                title=subject.value.title(),
                sequence=subj_index,
                subject_code=subject.value,
                metadata_json={},
            )
            session.add(subject_section)
            session.flush()

        for sec_index, section_code in enumerate(JeeMainSectionCode, start=1):
            child = session.scalar(
                select(ExamSection).where(
                    ExamSection.exam_version_id == version.id,
                    ExamSection.parent_section_id == subject_section.id,
                    ExamSection.code == section_code.value,
                )
            )
            if child is None:
                child = ExamSection(
                    exam_version_id=version.id,
                    parent_section_id=subject_section.id,
                    parent_exam_version_id=version.id,
                    code=section_code.value,
                    title=section_code.value.replace("_", " ").title(),
                    sequence=sec_index,
                    subject_code=subject.value,
                    metadata_json={},
                )
                session.add(child)
                session.flush()

            qtype = (
                JeeMainQuestionTypeQuota.MCQ
                if section_code == JeeMainSectionCode.SECTION_A
                else JeeMainQuestionTypeQuota.NUMERICAL
            )
            exact = (
                CANDIDATE_SECTION_A_MCQ
                if section_code == JeeMainSectionCode.SECTION_A
                else CANDIDATE_SECTION_B_NUMERICAL
            )
            rule_exists = session.scalar(
                select(ExamBlueprintRule).where(
                    ExamBlueprintRule.exam_version_id == version.id,
                    ExamBlueprintRule.section_id == child.id,
                    ExamBlueprintRule.rule_type == _rule_type(section_code, qtype),
                )
            )
            if rule_exists is None:
                session.add(
                    ExamBlueprintRule(
                        exam_version_id=version.id,
                        section_id=child.id,
                        section_exam_version_id=version.id,
                        rule_type=_rule_type(section_code, qtype),
                        selector_json={"subject_code": subject.value, "question_type": qtype.value},
                        exact_count=exact,
                        marks_per_question=CANDIDATE_MARKS_CORRECT,
                        negative_marks=CANDIDATE_MARKS_INCORRECT,
                        metadata_json={
                            "unattempted_marks": CANDIDATE_MARKS_UNATTEMPTED,
                            "verified_official": False,
                        },
                    )
                )

    version_rule = session.scalar(
        select(ExamBlueprintRule).where(
            ExamBlueprintRule.exam_version_id == version.id,
            ExamBlueprintRule.section_id.is_(None),
            ExamBlueprintRule.rule_type == "paper_total_questions",
        )
    )
    if version_rule is None:
        session.add(
            ExamBlueprintRule(
                exam_version_id=version.id,
                rule_type="paper_total_questions",
                selector_json={"subjects": [s.value for s in JeeMainSubjectCode]},
                exact_count=CANDIDATE_PAPER1_TOTAL_QUESTIONS,
                metadata_json={
                    "per_subject_exact_count": CANDIDATE_SUBJECT_QUESTION_COUNT,
                    "verified_official": False,
                },
            )
        )


def get_exam_version(
    session: Session, *, pack_code: str, version_code: str
) -> ExamVersion | None:
    pack = session.scalar(select(ExamPack).where(ExamPack.code == pack_code))
    if pack is None:
        return None
    return session.scalar(
        select(ExamVersion).where(
            ExamVersion.exam_pack_id == pack.id,
            ExamVersion.version_code == version_code,
        )
    )
