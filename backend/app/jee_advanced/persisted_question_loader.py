"""Load persisted Question rows for verification (Issue #47 PROD-47-01)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.jee_advanced.stored_answer_resolution import question_type_family
from app.models import Question
from app.models.enums import QuestionStatus


@dataclass(frozen=True, slots=True)
class PersistedAnswerScope:
    organization_id: str
    institution_id: str | None
    exam_version_id: str | None = None
    expected_family: str | None = None


def load_persisted_question(
    session: Session,
    question_id: str,
    scope: PersistedAnswerScope,
) -> tuple[Question | None, tuple[str, ...]]:
    question = session.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options))
    )
    if question is None:
        return None, ("question_not_found",)

    if question.status != QuestionStatus.APPROVED.value:
        return question, ("question_not_approved",)

    meta = dict(question.metadata_json or {})
    q_org = str(meta.get("organization_id") or "").strip()
    if not q_org or q_org != scope.organization_id.strip():
        return question, ("question_tenant_mismatch",)

    if scope.institution_id is not None:
        q_inst = str(meta.get("institution_id") or "").strip()
        if not q_inst or q_inst != scope.institution_id.strip():
            return question, ("question_institution_mismatch",)

    if scope.exam_version_id and str(question.exam_version_id) != scope.exam_version_id:
        return question, ("question_exam_version_mismatch",)

    if scope.expected_family:
        family = question_type_family(question)
        if family != scope.expected_family:
            return question, ("question_type_mismatch",)

    return question, ()