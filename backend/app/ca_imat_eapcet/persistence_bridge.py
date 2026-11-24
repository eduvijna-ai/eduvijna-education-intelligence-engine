from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    IMAT_OPTIONS_PER_QUESTION,
    IMAT_PACK_CODE,
)
from app.ca_imat_eapcet.content_validation import validate_and_bind_question_ref
from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict
from app.models import Question, QuestionOption, TestDefinition, TestQuestion
from app.models.enums import QuestionOrigin, QuestionStatus, QuestionType, TestStatus
from app.models.examination import ExamVersion

_SYNTHETIC_SOURCE_PREFIX = "synthetic"
_ISSUANCE_NOTE = (
    "D14 harness-only: re-validates content, binds tenant/version/fingerprint; "
    "not production multi-tenant issuance (concurrency/PG unproven)."
)


def _options_required_for_pack(exam_pack_code: str) -> int:
    if exam_pack_code == IMAT_PACK_CODE:
        return IMAT_OPTIONS_PER_QUESTION
    return 4


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


def _content_fingerprint(questions: list[QuestionRef]) -> str:
    parts = [f"{q.fingerprint}:{q.marks_if_correct}:{q.marks_if_incorrect}" for q in questions]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _binding_digest(
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    source_version: str,
    idempotency_key: str,
    content_fp: str,
) -> str:
    payload = json.dumps(
        {
            "org": organization_id,
            "inst": institution_id,
            "exam_version_id": exam_version_id,
            "source_version": source_version,
            "idempotency_key": idempotency_key,
            "content_fp": content_fp,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _exam_version_allows_synthetic_issuance(session: Session, exam_version_id: str) -> bool:
    ver = session.get(ExamVersion, exam_version_id)
    if ver is None:
        return False
    meta = dict(ver.metadata_json or {})
    return meta.get("trust_mode") == "synthetic_fixture"


def _revalidate_questions(
    questions: list[QuestionRef],
    *,
    exam_pack_code: str,
) -> tuple[list[QuestionRef], list[IssueCode]]:
    opt_n = _options_required_for_pack(exam_pack_code)
    validated: list[QuestionRef] = []
    issues: list[IssueCode] = []
    for q in questions:
        bound, verdict, v_issues = validate_and_bind_question_ref(q, options_required=opt_n)
        issues.extend(v_issues)
        if verdict is not PlanVerdict.PASS:
            issues.append(IssueCode.VALIDATION_NOT_PROVEN)
            return [], list(dict.fromkeys(issues))
        validated.append(bound)
    return validated, issues


def _load_persisted_question_ids(
    session: Session,
    test: TestDefinition,
) -> tuple[str, ...]:
    return tuple(
        str(row)
        for row in session.scalars(
            select(TestQuestion.question_id)
            .where(TestQuestion.test_definition_id == test.id)
            .order_by(TestQuestion.sequence)
        ).all()
    )


def attempt_canonical_issuance(
    *,
    session: Session,
    questions: list[QuestionRef],
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    source_version: str,
    idempotency_key: str,
    exam_pack_code: str = CA_FOUNDATION_PACK_CODE,
) -> PersistenceEnvelope:
    content_fp = _content_fingerprint(questions)
    binding = _binding_digest(
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        source_version=source_version,
        idempotency_key=idempotency_key,
        content_fp=content_fp,
    )

    def _result(
        *,
        verdict: PlanVerdict,
        committed: bool,
        persisted_question_ids: tuple[str, ...] = (),
        issue_codes: tuple[IssueCode, ...] = (),
    ) -> PersistenceEnvelope:
        return PersistenceEnvelope(
            idempotency_key=idempotency_key,
            content_fingerprint=content_fp,
            tenant_id=organization_id,
            source_version=source_version,
            verdict=verdict,
            committed=committed,
            persisted_question_ids=persisted_question_ids,
            issue_codes=issue_codes,
        )

    if not idempotency_key or not idempotency_key.strip():
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
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
    if not source_version.lower().startswith(_SYNTHETIC_SOURCE_PREFIX):
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
        )
    if not _exam_version_allows_synthetic_issuance(session, exam_version_id):
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=(IssueCode.UNAPPROVED_SOURCE,),
        )

    validated, pre_issues = _revalidate_questions(questions, exam_pack_code=exam_pack_code)
    if not validated:
        return _result(
            verdict=PlanVerdict.NOT_READY,
            committed=False,
            issue_codes=tuple(pre_issues) or (IssueCode.VALIDATION_NOT_PROVEN,),
        )

    existing = session.scalar(
        select(TestDefinition).where(TestDefinition.code == idempotency_key)
    )
    if existing is not None:
        meta = dict(existing.metadata_json or {})
        if meta.get("organization_id") != organization_id:
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.TENANT_ISOLATION,),
            )
        if meta.get("institution_id") != institution_id:
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.TENANT_ISOLATION,),
            )
        if meta.get("exam_version_id") != exam_version_id:
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
            )
        if meta.get("content_fingerprint") != content_fp:
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.FINGERPRINT_TAMPER,),
            )
        if meta.get("binding_digest") != binding:
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
            )
        ids = _load_persisted_question_ids(session, existing)
        if len(ids) != len(validated):
            return _result(
                verdict=PlanVerdict.FAIL,
                committed=False,
                issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
            )
        return _result(
            verdict=PlanVerdict.PASS,
            committed=True,
            persisted_question_ids=ids,
        )

    nested = session.begin_nested()
    try:
        persisted_ids: list[str] = []
        for qref in validated:
            row = Question(
                external_code=qref.question_id,
                origin_type=QuestionOrigin.GENERATED.value,
                question_type=QuestionType.SINGLE_CHOICE.value,
                stem_text=qref.stem_text,
                exam_version_id=exam_version_id,
                status=QuestionStatus.DRAFT.value,
                answer_json={"correct_key": qref.correct_key},
                metadata_json={
                    "d14_synthetic_fixture": True,
                    "d14_synthetic_only": True,
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "source_version": source_version,
                    "content_fingerprint": qref.fingerprint,
                    "binding_digest": binding,
                    "issuance_note": _ISSUANCE_NOTE,
                },
            )
            session.add(row)
            session.flush()
            for key, text in (qref.options or {}).items():
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
            title=f"Day14 synthetic harness {idempotency_key}",
            exam_version_id=exam_version_id,
            status=TestStatus.DRAFT.value,
            metadata_json={
                "organization_id": organization_id,
                "institution_id": institution_id,
                "source_version": source_version,
                "exam_version_id": exam_version_id,
                "content_fingerprint": content_fp,
                "binding_digest": binding,
                "d14_synthetic_only": True,
                "exam_pack_code": exam_pack_code,
                "issuance_note": _ISSUANCE_NOTE,
            },
        )
        session.add(test)
        session.flush()
        for seq, (qid, qref) in enumerate(zip(persisted_ids, validated, strict=True), start=1):
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
        nested.commit()
        session.commit()
    except Exception:
        nested.rollback()
        session.rollback()
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
        )

    check_test = session.scalar(
        select(TestDefinition).where(TestDefinition.code == idempotency_key)
    )
    if check_test is None:
        return _result(
            verdict=PlanVerdict.FAIL,
            committed=False,
            issue_codes=(IssueCode.VALIDATION_NOT_PROVEN,),
        )
    assoc_count = session.scalar(
        select(func.count())
        .select_from(TestQuestion)
        .where(TestQuestion.test_definition_id == check_test.id)
    )
    if int(assoc_count or 0) != len(validated):
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