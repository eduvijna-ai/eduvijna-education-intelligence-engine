"""Validate both persisted questions before integrated pair issuance (#48)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.jee_advanced.independent_solver_proof import validation_run_covers_question
from app.jee_advanced.persisted_question_loader import (
    PersistedAnswerScope,
    load_persisted_question,
)
from app.jee_advanced.stored_answer_resolution import question_day9_veto
from app.models import Question


def validate_questions_for_pair_issuance(
    session: Session,
    *,
    organization_id: str,
    institution_id: str | None,
    exam_version_id: str,
    question_ids: tuple[str, str],
) -> tuple[bool, tuple[str, ...], tuple[Question, ...]]:
    issues: list[str] = []
    if len(set(question_ids)) != 2:
        issues.append("duplicate_cross_paper_question")

    loaded: list[Question] = []
    for qid in question_ids:
        question, load_issues = load_persisted_question(
            session,
            qid,
            PersistedAnswerScope(
                organization_id=organization_id,
                institution_id=institution_id,
                exam_version_id=exam_version_id,
                expected_family="mcq",
            ),
        )
        if load_issues:
            issues.extend(load_issues)
            continue
        assert question is not None
        if question_day9_veto(question):
            issues.append(f"day9_veto:{qid}")
            continue
        ok, reason = validation_run_covers_question(
            session,
            run_id=str((question.metadata_json or {}).get("day6_validation_audit_id") or ""),
            question=question,
            organization_id=organization_id,
            institution_id=institution_id,
        )
        if not ok:
            issues.append(reason or f"validation_failed:{qid}")
            continue
        loaded.append(question)

    if issues:
        return False, tuple(dict.fromkeys(issues)), ()
    if len(loaded) != 2:
        return False, ("question_validation_incomplete",), ()
    return True, (), (loaded[0], loaded[1])