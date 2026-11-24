from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict
from app.models import Question, QuestionOption, TestDefinition, TestQuestion
from app.models.enums import QuestionOrigin, QuestionStatus, QuestionType, TestStatus


@dataclass(frozen=True, slots=True)
class PersistenceEnvelope:
    """D14-30: canonical issuance outcome; no envelope-only success."""

    idempotency_key: str
    content_fingerprint: str
    tenant_id: str
    source_version: str
    verdict: PlanVerdict
    committed: bool
    persisted_question_ids: tuple[str, ...]
    issue_codes: tuple[IssueCode, ...]


def attempt_canonical_issuance(
    *,
    session: Session,
    questions: list[QuestionRef],
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    source_version: str,
    idempotency_key: str,
) -> PersistenceEnvelope:
    fp = hashlib.sha256(
        "|".join(q.fingerprint for q in questions).encode()
    ).hexdigest()

    def _result(
        *,
        verdict: PlanVerdict,
        committed: bool,
        persisted_question_ids: tuple[str, ...] = (),
        issue_codes: tuple[IssueCode, ...] = (),
    ) -> PersistenceEnvelope:
        return PersistenceEnvelope(
            idempotency_key=idempotency_key,
            content_fingerprint=fp,
            tenant_id=organization_id,
            source_version=source_version,
            verdict=verdict,
            committed=committed,
            persisted_question_ids=persisted_question_ids,
            issue_codes=issue_codes,
        )

    if not questions:
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=(IssueCode.ENVELOPE_ONLY_SUCCESS,),
        )
    if not organization_id or not institution_id or not exam_version_id or not source_version:
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=(IssueCode.MISSING_TENANT_CONTEXT,),
        )
    if not all(q.independently_validated for q in questions):
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN, IssueCode.ENVELOPE_ONLY_SUCCESS),
        )

    existing = session.scalar(select(TestDefinition).where(TestDefinition.code == idempotency_key))
    if existing is not None:
        count = session.scalar(
            select(func.count())
            .select_from(TestQuestion)
            .where(TestQuestion.test_definition_id == existing.id)
        )
        if int(count or 0) == len(questions):
            ids = tuple(
                str(row)
                for row in session.scalars(
                    select(TestQuestion.question_id).where(
                        TestQuestion.test_definition_id == existing.id
                    )
                ).all()
            )
            return _result(
                verdict=PlanVerdict.PASS,
                committed=True,
                persisted_question_ids=ids,
            )
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
        )

    try:
        persisted_ids: list[str] = []
        for _seq, qref in enumerate(questions, start=1):
            if not qref.stem_text or not qref.options or not qref.correct_key:
                session.rollback()
                return _result(
                    verdict=PlanVerdict.FAIL,
                    committed=False,
                    issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
                )
            row = Question(
                external_code=qref.question_id,
                origin_type=QuestionOrigin.GENERATED.value,
                question_type=QuestionType.SINGLE_CHOICE.value,
                stem_text=qref.stem_text,
                exam_version_id=exam_version_id,
                status=QuestionStatus.APPROVED.value,
                answer_json={"correct_key": qref.correct_key},
                metadata_json={
                    "d14_synthetic_fixture": True,
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "source_version": source_version,
                    "content_fingerprint": qref.fingerprint,
                },
            )
            session.add(row)
            session.flush()
            for key, text in qref.options.items():
                session.add(
                    QuestionOption(
                        question_id=str(row.id),
                        option_key=key,
                        text=text,
                        is_correct=key == qref.correct_key,
                    )
                )
            persisted_ids.append(str(row.id))

        test = TestDefinition(
            code=idempotency_key,
            title=f"Day14 synthetic practice {idempotency_key}",
            exam_version_id=exam_version_id,
            status=TestStatus.DRAFT.value,
            metadata_json={
                "organization_id": organization_id,
                "institution_id": institution_id,
                "source_version": source_version,
            },
        )
        session.add(test)
        session.flush()
        for seq, (qid, qref) in enumerate(zip(persisted_ids, questions, strict=True), start=1):
            session.add(
                TestQuestion(
                    test_definition_id=str(test.id),
                    question_id=qid,
                    sequence=seq,
                    section_code=qref.paper_or_section,
                    marks=qref.marks_if_correct,
                    negative_marks=qref.marks_if_incorrect,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
        )

    row_count = session.scalar(
        select(func.count()).select_from(Question).where(
            Question.external_code.in_([q.question_id for q in questions])
        )
    )
    if int(row_count or 0) != len(questions):
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
        )
    return _result(
        verdict=PlanVerdict.PASS,
        committed=True,
        persisted_question_ids=tuple(persisted_ids),
    )