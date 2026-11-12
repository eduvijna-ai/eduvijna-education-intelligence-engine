from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.constants import DERIVED_TOPIC_ALGEBRA
from app.jee_main_exam_intelligence.contracts import PaperPlanSlot
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSubjectCode,
    PaperPlanIssueCode,
)
from app.jee_main_exam_intelligence.syllabus_mapping import DERIVED_TOPIC_GROUPS
from app.jee_main_exam_intelligence.trusted_validation import (
    SYNTHETIC_JEE_MAIN_TRUST_TOKEN,
    JeeMainQuestionTrustContext,
    synthetic_trust_permitted,
)
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption
from app.root_cause_intelligence.day6_binding_verify import verify_production_day6_binding


def _question_topic_tags(metadata: dict[str, Any]) -> set[str]:
    tags = metadata.get("official_topic_codes") or []
    return {str(t) for t in tags}


def _canonical_quota_type(question: Question) -> str | None:
    if question.question_type == QuestionType.MULTIPLE_CHOICE.value:
        return JeeMainQuestionTypeQuota.MCQ.value
    if question.question_type == QuestionType.NUMERICAL.value:
        return JeeMainQuestionTypeQuota.NUMERICAL.value
    return None


def _trusts_item(
    session: Session,
    *,
    question: Question,
    execution_mode: TrustExecutionMode,
    organization_id: str | None,
    institution_id: str | None,
    exam_version_id: str | None,
    derived_topic_group: str | None,
) -> tuple[bool, PaperPlanIssueCode | None]:
    meta = question.metadata_json or {}
    synthetic_ok = synthetic_trust_permitted(execution_mode)
    if meta.get("synthetic_fixture") or meta.get("synthetic_only"):
        if not synthetic_ok:
            return False, PaperPlanIssueCode.INVALID_ANSWER
        token = meta.get("jee_main_trust_harness_token")
        if token != SYNTHETIC_JEE_MAIN_TRUST_TOKEN:
            return False, PaperPlanIssueCode.INVALID_ANSWER
        return True, None

    if synthetic_ok:
        return False, PaperPlanIssueCode.INVALID_ANSWER

    if organization_id is None:
        return False, PaperPlanIssueCode.FOREIGN_TENANT_CONTENT
    if meta.get("organization_id") != organization_id:
        return False, PaperPlanIssueCode.FOREIGN_TENANT_CONTENT
    if institution_id and meta.get("institution_id") != institution_id:
        return False, PaperPlanIssueCode.FOREIGN_TENANT_CONTENT
    if exam_version_id is None or meta.get("exam_version_id") != exam_version_id:
        return False, PaperPlanIssueCode.STALE_EXAM_VERSION

    item_id = question.external_code or question.id
    ok, _ = verify_production_day6_binding(
        session,
        item_id=item_id,
        validation_run_id=meta.get("day6_validation_run_id"),
        input_hash=meta.get("day6_input_hash"),
        learning_outcome_ids=list(meta.get("learning_outcome_ids") or []),
        competency_codes=list(meta.get("competency_codes") or []),
        organization_id=organization_id,
        institution_id=institution_id,
        curriculum_version_id=meta.get("curriculum_version_id"),
    )
    if not ok:
        return False, PaperPlanIssueCode.INVALID_ANSWER

    if derived_topic_group:
        group = DERIVED_TOPIC_GROUPS.get(derived_topic_group)
        if group is None:
            return False, PaperPlanIssueCode.UNKNOWN_TOPIC
        allowed = set(group["constituent_official_topic_codes"])
        if not _question_topic_tags(meta).intersection(allowed):
            return False, PaperPlanIssueCode.OFF_TOPIC_FILLER

    return True, None


def load_validated_questions(
    session: Session,
    *,
    subject: JeeMainSubjectCode,
    topic_codes: list[str],
    derived_topic_group: str | None,
    organization_id: str | None,
    institution_id: str | None,
    exam_version_id: str | None,
    allowed_source_revision_ids: list[str],
    question_type_quota: JeeMainQuestionTypeQuota | None = None,
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
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
        trusted, trust_issue = _trusts_item(
            session,
            question=question,
            execution_mode=execution_mode,
            organization_id=organization_id,
            institution_id=institution_id,
            exam_version_id=exam_version_id,
            derived_topic_group=derived_topic_group,
        )
        if not trusted:
            continue

        meta = question.metadata_json or {}
        rev_ids = {str(r) for r in (meta.get("allowed_source_revision_ids") or [])}
        if allowed_source_revision_ids and not rev_ids.issuperset(set(allowed_source_revision_ids)):
            continue

        if derived_topic_group:
            if synthetic_trust_permitted(execution_mode):
                groups = meta.get("derived_topic_groups") or []
                if derived_topic_group not in groups:
                    continue
        elif topic_codes:
            if not _question_topic_tags(meta).intersection(topic_codes):
                continue

        if not _answer_valid(question):
            continue

        if question_type_quota is not None:
            mapped = _canonical_quota_type(question)
            if mapped != question_type_quota.value:
                continue
            alias = meta.get("jee_main_question_type")
            if alias and alias != mapped and not synthetic_trust_permitted(execution_mode):
                continue

        filtered.append(question)
    return filtered, issues


def _answer_valid(question: Question) -> bool:
    """Fail closed on inconsistent answers in *stored* paper-pool questions.

    Day6 provenance alone cannot certify a malformed option/answer mapping.
    This is a structural gate; independent academic solving remains separate.
    """
    qtype = question.question_type
    answer = question.answer_json or {}
    if qtype == QuestionType.MULTIPLE_CHOICE.value:
        options = question.options or []
        meta = question.metadata_json or {}
        synthetic_orchestration = (
            meta.get("orchestration_origin")
            and meta.get("jee_main_trust_harness_token") == SYNTHETIC_JEE_MAIN_TRUST_TOKEN
            and meta.get("synthetic_fixture") is True
        )
        if synthetic_orchestration:
            if len(options) < 2:
                return False
        elif len(options) != 4:
            return False

        keys = [str(option.option_key).strip().upper() for option in options]
        texts = [str(option.text).strip().casefold() for option in options]
        if (
            any(not key for key in keys)
            or any(not text for text in texts)
            or len(keys) != len(set(keys))
            or len(texts) != len(set(texts))
        ):
            return False
        correct = [option for option in options if option.is_correct]
        expected = answer.get("correct_option")
        return (
            len(correct) == 1
            and isinstance(expected, str)
            and expected.strip().upper() == str(correct[0].option_key).strip().upper()
        )

    if qtype == QuestionType.NUMERICAL.value:
        numeric = answer.get("numeric_value")
        if numeric is None or isinstance(numeric, bool):
            return False
        if not isinstance(numeric, (str, int, float, Decimal)):
            return False
        try:
            return Decimal(str(numeric)).is_finite()
        except (InvalidOperation, ValueError):
            return False
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


def seed_synthetic_question_pool(
    session: Session, *, organization_id: str, institution_id: str
) -> dict[str, Any]:
    """Seed deterministic questions for the Day11 synthetic harness only."""
    trust = JeeMainQuestionTrustContext.synthetic_fixture_harness()
    ctx: dict[str, Any] = {"question_ids": []}
    algebra_codes = ["complex-numbers-quadratic", "matrices-determinants"]
    base_meta = {
        "jee_main_trust_harness_token": trust.harness_token,
        "synthetic_fixture": True,
        "organization_id": organization_id,
        "institution_id": institution_id,
    }
    for index in range(1, 26):
        subject = JeeMainSubjectCode.MATHEMATICS
        is_algebra = index <= 12
        is_numerical = index > 20
        qtype = QuestionType.NUMERICAL if is_numerical else QuestionType.MULTIPLE_CHOICE
        meta = {
            **base_meta,
            "jee_main_subject_code": subject.value,
            "official_topic_codes": algebra_codes if is_algebra else ["sets-relations-functions"],
            "derived_topic_groups": [DERIVED_TOPIC_ALGEBRA] if is_algebra else [],
            "cognitive_level": "apply",
            "competency_codes": ["knowledge"],
            "primary_competency_code": "knowledge",
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
                    **base_meta,
                    "jee_main_subject_code": subj.value,
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
