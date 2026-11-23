"""Select persisted CUET questions with provable Day6 + solver bindings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.constants import CUET_QUESTIONS_PER_TEST
from app.cuet_clat.contracts import PracticeQuestionRef
from app.cuet_clat.cuet_validation_bridge import persisted_validation_covers_question
from app.cuet_clat.enums import IssueCode, PlanVerdict
from app.cuet_clat.persisted_context import PersistedCuetSelectionContext
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.models import Question
from app.models.enums import QuestionStatus


def _question_has_single_correct(question: Question) -> bool:
    correct = [opt for opt in question.options if opt.is_correct]
    return len(correct) == 1 and len(question.options) == 4


def select_validated_cuet_questions(
    session: Session,
    *,
    context: PersistedCuetSelectionContext,
    test_subject_code: str,
    requested_count: int,
) -> tuple[list[PracticeQuestionRef], list[IssueCode], PlanVerdict]:
    rows = session.scalars(
        select(Question)
        .where(
            Question.status == QuestionStatus.APPROVED.value,
            Question.exam_version_id == context.exam_version_id,
        )
        .order_by(Question.external_code, Question.id)
    ).all()

    chosen: list[PracticeQuestionRef] = []
    seen_ids: set[str] = set()
    seen_stems: set[str] = set()
    blocking: list[IssueCode] = []

    for row in rows:
        meta = dict(row.metadata_json or {})
        if not meta.get("d13_synthetic_fixture"):
            continue
        if meta.get("not_official_cuet_item") is not True:
            continue
        if str(meta.get("subject_code") or "") != test_subject_code:
            blocking.append(IssueCode.WRONG_SUBJECT)
            continue
        if str(meta.get("medium_code") or "english") != context.medium_code:
            blocking.append(IssueCode.WRONG_MEDIUM)
            continue
        if str(meta.get("academic_year") or "") != context.academic_year:
            blocking.append(IssueCode.WRONG_YEAR)
            continue

        ok, _reason = persisted_validation_covers_question(
            session,
            question=row,
            organization_id=context.organization_id,
            institution_id=context.institution_id,
        )
        if not ok:
            continue
        if not _question_has_single_correct(row):
            continue
        qid = str(row.id)
        if qid in seen_ids:
            blocking.append(IssueCode.DUPLICATE_QUESTION)
            continue
        stem_norm = (row.stem_text or "").strip().lower()
        if stem_norm in seen_stems:
            continue
        seen_ids.add(qid)
        seen_stems.add(stem_norm)
        correct = next(opt for opt in row.options if opt.is_correct)
        chosen.append(
            PracticeQuestionRef(
                question_id=qid,
                subject_code=test_subject_code,
                topic_code=str(meta.get("topic_code") or ""),
                fingerprint=question_content_fingerprint(row),
                correct_key=correct.option_key,
                marks_if_correct=float(meta.get("marks_correct") or 5.0),
                marks_if_incorrect=float(meta.get("marks_incorrect") or -1.0),
                stem_text=row.stem_text,
                options={opt.option_key: opt.text for opt in row.options},
                independently_validated=True,
                validation_audit_id=str(meta.get("day6_validation_audit_id") or ""),
                solver_evidence_id=str(meta.get("day6_solver_evidence_id") or ""),
            )
        )
        if len(chosen) >= requested_count:
            break

    if blocking:
        return [], list(dict.fromkeys(blocking)), PlanVerdict.FAIL
    if len(chosen) < requested_count:
        return [], [IssueCode.CUET_COUNT_MISMATCH], PlanVerdict.SHORTAGE
    return chosen, [], PlanVerdict.PASS


def persisted_target_count_for_single_test() -> int:
    return CUET_QUESTIONS_PER_TEST