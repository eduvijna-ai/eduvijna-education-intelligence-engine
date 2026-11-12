"""D12-CORE-03: Persisted Question selection for trusted Math10 / Algebra10 practice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import EDUVIJNA_DERIVED_TOPIC_GROUP, MATHEMATICS_SUBJECT
from app.jee_advanced.contracts import PracticeQuestionRef
from app.jee_advanced.enums import AdvancedIssueCode, AdvancedPlanVerdict
from app.models import Question
from app.models.enums import QuestionStatus


def _day6_trusted(meta: dict[str, object]) -> bool:
    audit = str(meta.get("day6_validation_audit_id") or "").strip()
    solver = str(meta.get("day6_solver_evidence_id") or "").strip()
    if not audit or not solver:
        return False
    if meta.get("day9_veto") is True:
        return False
    if not meta.get("d12_core_test_fixture"):
        return False
    return True


def select_trusted_questions(
    session: Session,
    *,
    organization_id: str,
    institution_id: str | None,
    exam_version_id: str,
    subject_code: str,
    topic_group: str | None,
    requested_count: int,
) -> tuple[list[PracticeQuestionRef], list[AdvancedIssueCode], AdvancedPlanVerdict]:
    """Return persisted Question rows with provable Day6 test evidence metadata."""

    issues: list[AdvancedIssueCode] = []
    if subject_code.lower() != MATHEMATICS_SUBJECT:
        return [], [AdvancedIssueCode.WRONG_SUBJECT], AdvancedPlanVerdict.FAIL

    rows = session.scalars(
        select(Question)
        .where(
            Question.status == QuestionStatus.APPROVED.value,
            Question.exam_version_id == exam_version_id,
        )
        .order_by(Question.external_code, Question.id)
    ).all()

    chosen: list[PracticeQuestionRef] = []
    seen: set[str] = set()
    for row in rows:
        meta = dict(row.metadata_json or {})
        org = str(meta.get("organization_id") or "")
        inst = meta.get("institution_id")
        if org != organization_id:
            continue
        if institution_id and inst and str(inst) != institution_id:
            continue
        if not _day6_trusted(meta):
            continue
        subj = str(meta.get("subject_code") or "").lower()
        if subj != subject_code.lower():
            continue
        if topic_group is not None:
            tg = str(meta.get("topic_group") or "").lower()
            if tg != topic_group.lower():
                continue
        if str(row.id) in seen:
            issues.append(AdvancedIssueCode.UNVALIDATED_QUESTION)
            continue
        if not row.answer_json:
            continue
        seen.add(str(row.id))
        chosen.append(
            PracticeQuestionRef(
                question_id=str(row.id),
                subject_code=subject_code,
                topic_group=topic_group,
                independently_validated=True,
                solver_audit_id=str(meta.get("day6_solver_evidence_id")),
                metadata_json={
                    "persisted_selection": True,
                    "d12_core_test_fixture": True,
                    "day6_validation_audit_id": meta.get("day6_validation_audit_id"),
                },
            )
        )
        if len(chosen) >= requested_count:
            break

    if len(chosen) < requested_count:
        return (
            chosen,
            [*issues, AdvancedIssueCode.COUNT_SHORTAGE],
            AdvancedPlanVerdict.SHORTAGE,
        )
    if topic_group and topic_group.lower() != EDUVIJNA_DERIVED_TOPIC_GROUP:
        return chosen, [AdvancedIssueCode.WRONG_TOPIC], AdvancedPlanVerdict.FAIL
    return chosen, issues, AdvancedPlanVerdict.PASS
