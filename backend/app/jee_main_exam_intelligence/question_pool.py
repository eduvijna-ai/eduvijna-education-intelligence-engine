from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.constants import DERIVED_TOPIC_ALGEBRA
from app.jee_main_exam_intelligence.contracts import PaperPlanSlot
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSubjectCode,
    PaperPlanIssueCode,
)
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption


def _question_topic_tags(metadata: dict[str, Any]) -> set[str]:
    tags = metadata.get("official_topic_codes") or []
    return {str(t) for t in tags}


def _question_derived_groups(metadata: dict[str, Any]) -> set[str]:
    groups = metadata.get("derived_topic_groups") or []
    return {str(g) for g in groups}


def load_validated_questions(
    session: Session,
    *,
    subject: JeeMainSubjectCode,
    topic_codes: list[str],
    derived_topic_group: str | None,
    organization_id: str | None,
    allowed_source_revision_ids: list[str],
    question_type_quota: JeeMainQuestionTypeQuota | None = None,
) -> tuple[list[Question], list[PaperPlanIssueCode]]:
    issues: list[PaperPlanIssueCode] = []
    stmt = select(Question).where(Question.status == QuestionStatus.APPROVED.value)
    questions = [
        q
        for q in session.scalars(stmt)
        if (q.metadata_json or {}).get("jee_main_subject_code") == subject.value
    ]
    filtered: list[Question] = []
    for question in questions:
        meta = question.metadata_json or {}
        if organization_id and meta.get("organization_id") not in (None, organization_id):
            issues.append(PaperPlanIssueCode.FOREIGN_TENANT_CONTENT)
            continue
        rev_ids = {str(r) for r in (meta.get("allowed_source_revision_ids") or [])}
        if allowed_source_revision_ids and not rev_ids.issuperset(set(allowed_source_revision_ids)):
            continue
        if derived_topic_group:
            if derived_topic_group not in _question_derived_groups(meta):
                continue
        elif topic_codes:
            if not _question_topic_tags(meta).intersection(topic_codes):
                continue
        if not _answer_valid(question):
            continue
        if not meta.get("day6_validated", False):
            continue
        if question_type_quota is not None:
            qmeta = meta.get("jee_main_question_type") or question.question_type
            mapped = "mcq" if qmeta in (QuestionType.MULTIPLE_CHOICE.value, "mcq") else "numerical"
            if mapped != question_type_quota.value:
                continue
        filtered.append(question)
    return filtered, issues


def _answer_valid(question: Question) -> bool:
    qtype = question.question_type
    if qtype == QuestionType.MULTIPLE_CHOICE.value:
        options = question.options or []
        correct = [opt for opt in options if opt.is_correct]
        return len(correct) == 1 and len(options) >= 4
    if qtype == QuestionType.NUMERICAL.value:
        answer = question.answer_json or {}
        return answer.get("numeric_value") is not None
    return False


def assign_questions_to_slots(
    slots: list[PaperPlanSlot],
    questions: list[Question],
    *,
    marks: float | None = None,
    negative_marks: float | None = None,
) -> tuple[list[PaperPlanSlot], list[PaperPlanIssueCode]]:
    issues: list[PaperPlanIssueCode] = []
    if len(questions) < len(slots):
        issues.append(PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL)
        return slots, issues
    used: set[str] = set()
    filled: list[PaperPlanSlot] = []
    for slot, question in zip(slots, questions[: len(slots)], strict=False):
        if question.id in used:
            issues.append(PaperPlanIssueCode.DUPLICATE_ITEM_ID)
            continue
        used.add(question.id)
        filled.append(
            slot.model_copy(
                update={
                    "question_id": question.id,
                    "marks": marks,
                    "negative_marks": negative_marks,
                }
            )
        )
    if len(filled) != len(slots):
        issues.append(PaperPlanIssueCode.COUNT_MISMATCH)
    return filled, issues


def seed_synthetic_question_pool(session: Session, *, organization_id: str) -> dict[str, Any]:
    """Seed deterministic approved questions for Day11 synthetic harness."""
    ctx: dict[str, Any] = {"question_ids": []}
    algebra_codes = ["complex-numbers-quadratic", "matrices-determinants"]
    for index in range(1, 26):
        subject = JeeMainSubjectCode.MATHEMATICS
        is_algebra = index <= 12
        is_numerical = index > 20
        qtype = QuestionType.NUMERICAL if is_numerical else QuestionType.MULTIPLE_CHOICE
        qmeta = "numerical" if is_numerical else "mcq"
        meta = {
            "jee_main_subject_code": subject.value,
            "jee_main_question_type": qmeta,
            "organization_id": organization_id,
            "day6_validated": True,
            "official_topic_codes": algebra_codes if is_algebra else ["sets-relations-functions"],
            "derived_topic_groups": [DERIVED_TOPIC_ALGEBRA] if is_algebra else [],
            "synthetic_fixture": True,
        }
        q = Question(
            external_code=f"d11-math-{index:03d}",
            origin_type="synthetic_fixture",
            question_type=qtype.value,
            stem_text=f"Synthetic JEE Main math item {index}",
            answer_json=(
                {"numeric_value": index}
                if is_numerical
                else {"correct_option": "A"}
            ),
            status=QuestionStatus.APPROVED.value,
            metadata_json=meta,
        )
        session.add(q)
        session.flush()
        if qtype == QuestionType.MULTIPLE_CHOICE:
            for key in ("A", "B", "C", "D"):
                session.add(
                    QuestionOption(
                        question_id=q.id,
                        option_key=key,
                        text=f"Option {key} for item {index}",
                        is_correct=key == "A",
                    )
                )
        ctx["question_ids"].append(q.id)

    for subj, count, prefix in (
        (JeeMainSubjectCode.PHYSICS, 30, "d11-phy"),
        (JeeMainSubjectCode.CHEMISTRY, 30, "d11-che"),
    ):
        for index in range(1, count + 1):
            qtype = (
                QuestionType.MULTIPLE_CHOICE
                if index <= int(count * 0.8)
                else QuestionType.NUMERICAL
            )
            qmeta = "mcq" if qtype == QuestionType.MULTIPLE_CHOICE else "numerical"
            q = Question(
                external_code=f"{prefix}-{index:03d}",
                origin_type="synthetic_fixture",
                question_type=qtype.value,
                stem_text=f"Synthetic {subj.value} item {index}",
                answer_json=(
                    {"correct_option": "A"}
                    if qtype == QuestionType.MULTIPLE_CHOICE
                    else {"numeric_value": index}
                ),
                status=QuestionStatus.APPROVED.value,
                metadata_json={
                    "jee_main_subject_code": subj.value,
                    "jee_main_question_type": qmeta,
                    "organization_id": organization_id,
                    "day6_validated": True,
                    "synthetic_fixture": True,
                },
            )
            session.add(q)
            session.flush()
            if qtype == QuestionType.MULTIPLE_CHOICE:
                for key in ("A", "B", "C", "D"):
                    session.add(
                        QuestionOption(
                            question_id=q.id,
                            option_key=key,
                            text=f"Option {key}",
                            is_correct=key == "A",
                        )
                    )
            ctx.setdefault(f"{subj.value}_ids", []).append(q.id)
    return ctx
