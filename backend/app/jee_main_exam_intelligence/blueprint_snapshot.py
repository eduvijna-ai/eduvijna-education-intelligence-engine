from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    return all((rule.metadata_json or {}).get("verified_official") is True for rule in rules)


def load_production_blueprint_snapshot(
    session: Session, exam_version: ExamVersion
) -> VerifiedBlueprintSnapshot | None:
    """Never reconstruct an official replica from candidate count/mark defaults.

    Every verified version must provide one total rule and every subject/section
    rule with consistent marking. Missing or contradictory curator rules veto
    production rather than silently falling back to last year's demo pattern.
    """
    version_meta = exam_version.metadata_json or {}
    if version_meta.get("official_pattern_verified") is not True:
        return None
    if not blueprint_fully_verified(session, exam_version):
        return None

    rules = session.scalars(
        select(ExamBlueprintRule).where(ExamBlueprintRule.exam_version_id == exam_version.id)
    ).all()
    total_rules = [
        rule for rule in rules
        if rule.section_id is None and rule.rule_type == "paper_total_questions"
    ]
    if len(total_rules) != 1:
        return None
    total_rule = total_rules[0]
    if total_rule.exact_count is None or total_rule.exact_count <= 0:
        return None

    pinned_raw = version_meta.get("pinned_source_revision_ids")
    if not isinstance(pinned_raw, list) or len(set(pinned_raw)) < 2:
        return None
    source_ids = tuple(sorted(str(rid) for rid in set(pinned_raw) if rid))
    if len(source_ids) < 2:
        return None

    duration = exam_version.duration_minutes
    total_marks = exam_version.total_marks
    if duration is None or duration <= 0 or total_marks is None or total_marks <= 0:
        return None

    marking = version_meta.get("marking")
    if not isinstance(marking, dict) or "unattempted" not in marking:
        return None
    try:
        unattempted = float(marking["unattempted"])
        per_subject_exact = int((total_rule.metadata_json or {})["per_subject_exact_count"])
    except (KeyError, TypeError, ValueError):
        return None
    if per_subject_exact <= 0:
        return None

    subjects = {s.value for s in JeeMainSubjectCode}
    qtypes = {q.value for q in JeeMainQuestionTypeQuota}
    expected = {(subj, qtype) for subj in subjects for qtype in qtypes}
    counts: dict[tuple[str, str], int] = {}
    marks_correct: float | None = None
    marks_incorrect: float | None = None

    section_rules = [rule for rule in rules if rule.section_id is not None]
    if len(section_rules) != len(expected) or len(rules) != len(expected) + 1:
        return None
    for rule in section_rules:
        selector = rule.selector_json or {}
        subject = str(selector.get("subject_code") or "")
        qtype = str(selector.get("question_type") or "")
        key = (subject, qtype)
        if key not in expected or key in counts:
            return None
        if rule.section is None or rule.section.subject_code != subject:
            return None
        if rule.section_exam_version_id != exam_version.id:
            return None
        if rule.exact_count is None or rule.exact_count < 0:
            return None
        if rule.marks_per_question is None or rule.negative_marks is None:
            return None
        correct = float(rule.marks_per_question)
        incorrect = float(rule.negative_marks)
        if correct <= 0 or incorrect > 0:
            return None
        if marks_correct is None:
            marks_correct, marks_incorrect = correct, incorrect
        elif (correct, incorrect) != (marks_correct, marks_incorrect):
            return None
        counts[key] = int(rule.exact_count)
    if set(counts) != expected or marks_correct is None or marks_incorrect is None:
        return None

    totals_by_subject = {
        subject: sum(counts[(subject, qtype)] for qtype in qtypes)
        for subject in subjects
    }
    if any(count != per_subject_exact for count in totals_by_subject.values()):
        return None
    if sum(totals_by_subject.values()) != int(total_rule.exact_count):
        return None
    if abs(float(total_marks) - int(total_rule.exact_count) * marks_correct) > 1e-6:
        return None

    mcq_per_subject = {counts[(s, JeeMainQuestionTypeQuota.MCQ.value)] for s in subjects}
    num_per_subject = {
        counts[(s, JeeMainQuestionTypeQuota.NUMERICAL.value)] for s in subjects
    }
    # The existing allocator accepts one common section count for all subjects.
    # If NTA ever publishes unequal subject quotas, reject until the allocator
    # explicitly models the versioned per-subject distribution.
    if len(mcq_per_subject) != 1 or len(num_per_subject) != 1:
        return None
    return VerifiedBlueprintSnapshot(
        total_questions=int(total_rule.exact_count),
        total_marks=float(total_marks),
        duration_minutes=int(duration),
        marks_correct=marks_correct,
        marks_incorrect=marks_incorrect,
        marks_unattempted=unattempted,
        per_subject_exact=per_subject_exact,
        section_a_mcq=mcq_per_subject.pop(),
        section_b_numerical=num_per_subject.pop(),
        blueprint_rule_ids=tuple(sorted(rule.id for rule in rules)),
        source_revision_ids=source_ids,
    )
