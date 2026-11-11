from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_MARKS_CORRECT,
    CANDIDATE_MARKS_INCORRECT,
    CANDIDATE_PAPER1_TOTAL_QUESTIONS,
    CANDIDATE_SECTION_A_MCQ,
    CANDIDATE_SECTION_B_NUMERICAL,
)
from app.jee_main_exam_intelligence.enums import JeeMainQuestionTypeQuota, JeeMainSubjectCode
from app.models.examination import ExamBlueprintRule, ExamVersion


@dataclass(frozen=True)
class VerifiedBlueprintSnapshot:
    total_questions: int
    total_marks: float
    duration_minutes: int
    marks_correct: float
    marks_incorrect: float
    marks_unattempted: float
    per_subject_exact: int
    section_a_mcq: int
    section_b_numerical: int
    blueprint_rule_ids: tuple[str, ...]
    source_revision_ids: tuple[str, ...]


def blueprint_fully_verified(session: Session, exam_version: ExamVersion) -> bool:
    rules = session.scalars(
        select(ExamBlueprintRule).where(ExamBlueprintRule.exam_version_id == exam_version.id)
    ).all()
    if not rules:
        return False
    return all((rule.metadata_json or {}).get("verified_official") for rule in rules)


def load_production_blueprint_snapshot(
    session: Session, exam_version: ExamVersion
) -> VerifiedBlueprintSnapshot | None:
    version_meta = exam_version.metadata_json or {}
    if not version_meta.get("official_pattern_verified"):
        return None
    if not blueprint_fully_verified(session, exam_version):
        return None
    rules = session.scalars(
        select(ExamBlueprintRule).where(ExamBlueprintRule.exam_version_id == exam_version.id)
    ).all()
    total_rule = next((r for r in rules if r.rule_type == "paper_total_questions"), None)
    if total_rule is None or total_rule.exact_count is None:
        return None
    per_subject = int((total_rule.metadata_json or {}).get("per_subject_exact_count") or 0)
    section_rules = [r for r in rules if r.section_id and r.exact_count]
    mcq = numerical = 0
    for rule in section_rules:
        selector = rule.selector_json or {}
        qtype = str(selector.get("question_type") or "")
        if qtype == JeeMainQuestionTypeQuota.MCQ.value:
            mcq += int(rule.exact_count or 0)
        elif qtype == JeeMainQuestionTypeQuota.NUMERICAL.value:
            numerical += int(rule.exact_count or 0)
    marking = version_meta.get("marking") or {}
    source_ids = tuple(
        sorted(
            {
                str(rid)
                for rid in (version_meta.get("pinned_source_revision_ids") or [])
                if rid
            }
        )
    )
    sample = next((r for r in section_rules if r.marks_per_question is not None), None)
    return VerifiedBlueprintSnapshot(
        total_questions=int(total_rule.exact_count),
        total_marks=float(exam_version.total_marks or 0),
        duration_minutes=int(exam_version.duration_minutes or 0),
        marks_correct=float(
            sample.marks_per_question
            if sample is not None and sample.marks_per_question is not None
            else CANDIDATE_MARKS_CORRECT
        ),
        marks_incorrect=float(
            sample.negative_marks
            if sample is not None and sample.negative_marks is not None
            else CANDIDATE_MARKS_INCORRECT
        ),
        marks_unattempted=float(marking.get("unattempted", 0.0)),
        per_subject_exact=per_subject
        or CANDIDATE_PAPER1_TOTAL_QUESTIONS // len(JeeMainSubjectCode),
        section_a_mcq=mcq // len(JeeMainSubjectCode) if mcq else CANDIDATE_SECTION_A_MCQ,
        section_b_numerical=numerical // len(JeeMainSubjectCode)
        if numerical
        else CANDIDATE_SECTION_B_NUMERICAL,
        blueprint_rule_ids=tuple(sorted(r.id for r in rules)),
        source_revision_ids=source_ids,
    )
