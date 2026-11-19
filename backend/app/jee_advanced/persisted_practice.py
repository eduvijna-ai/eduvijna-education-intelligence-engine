"""D12-CORE-03: Persisted Question selection for trusted Math10 / Algebra10 practice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.enums import ValidationStatus
from app.jee_advanced.constants import EDUVIJNA_DERIVED_TOPIC_GROUP, MATHEMATICS_SUBJECT
from app.jee_advanced.contracts import PracticeQuestionRef
from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedPlanVerdict,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.jee_advanced.source_storage import metadata_marks_synthetic
from app.models import Question, ValidationAuditRun
from app.models.enums import QuestionStatus


def _question_has_correct_option(question: Question) -> bool:
    return any(opt.is_correct for opt in question.options)


def _solver_evidence_proven(
    record: ValidationAuditRun, *, question_id: str, solver_id: str
) -> bool:
    if not solver_id:
        return False
    for row in record.results_json or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("evidence_id") or "") != solver_id:
            continue
        if str(row.get("kind") or "") != "independent_solver":
            continue
        if str(row.get("item_id") or "") == question_id:
            return True
    return False


def _validation_run_covers_item(
    session: Session,
    *,
    run_id: str,
    question: Question,
    organization_id: str,
    institution_id: str | None,
) -> tuple[bool, str | None]:
    record = session.scalar(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == run_id)
    )
    if record is None:
        return False, "missing_validation_run"
    if record.blocking_failure:
        return False, "blocking_validation_failure"
    if record.aggregate_status != ValidationStatus.PASS.value:
        return False, "validation_not_pass"

    content_hash = question_content_fingerprint(question)
    if record.input_hash != content_hash:
        return False, "validation_input_hash_mismatch"

    meta = dict(record.metadata_json or {})
    validated = meta.get("validated_items") or []
    item_row = None
    for row in validated:
        if not isinstance(row, dict):
            continue
        if str(row.get("item_id")) == str(question.id):
            item_row = row
            break
    if item_row is None:
        return False, "validation_run_item_mismatch"
    item_hash = str(item_row.get("input_hash") or "")
    if item_hash and item_hash != content_hash:
        return False, "validation_item_hash_mismatch"

    scope = dict(meta.get("scope") or {})
    scope_org = str(scope.get("organization_id") or meta.get("organization_id") or "")
    if scope_org and scope_org != organization_id:
        return False, "validation_org_mismatch"
    if institution_id is not None:
        scope_inst = str(
            scope.get("institution_id") or record.institution_id or ""
        ).strip()
        if not scope_inst or scope_inst != institution_id:
            return False, "validation_institution_mismatch"

    solver_id = str((question.metadata_json or {}).get("day6_solver_evidence_id") or "")
    if not _solver_evidence_proven(record, question_id=str(question.id), solver_id=solver_id):
        return False, "independent_solver_not_persisted"

    return True, None


def select_trusted_questions(
    session: Session,
    *,
    organization_id: str,
    institution_id: str | None,
    exam_version_id: str,
    subject_code: str,
    topic_group: str | None,
    requested_count: int,
    trust_mode: JeeAdvancedSourceTrustMode,
    allow_labeled_test_fixtures: bool = False,
) -> tuple[list[PracticeQuestionRef], list[AdvancedIssueCode], AdvancedPlanVerdict]:
    """Return persisted Question rows with provable Day6 audit evidence."""

    if subject_code.lower() != MATHEMATICS_SUBJECT:
        return [], [AdvancedIssueCode.WRONG_SUBJECT], AdvancedPlanVerdict.FAIL

    if trust_mode is not JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE:
        return (
            [],
            [AdvancedIssueCode.UNAPPROVED_SOURCE],
            AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
        )

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
    blocking_issues: list[AdvancedIssueCode] = []

    for row in rows:
        meta = dict(row.metadata_json or {})
        org = str(meta.get("organization_id") or "")
        inst = meta.get("institution_id")
        if org != organization_id:
            if org:
                blocking_issues.append(AdvancedIssueCode.TENANT_ISOLATION)
            continue
        if institution_id is not None:
            if inst is None or str(inst) != institution_id:
                blocking_issues.append(AdvancedIssueCode.TENANT_ISOLATION)
                continue

        is_test_fixture = bool(meta.get("d12_core_test_fixture"))
        if metadata_marks_synthetic(meta) and not is_test_fixture:
            continue
        if is_test_fixture and not allow_labeled_test_fixtures:
            continue
        if not is_test_fixture:
            continue

        run_id = str(meta.get("day6_validation_audit_id") or "").strip()
        if not run_id:
            continue
        ok, _reason = _validation_run_covers_item(
            session,
            run_id=run_id,
            question=row,
            organization_id=organization_id,
            institution_id=institution_id,
        )
        if not ok:
            continue

        if meta.get("day9_veto") is True:
            continue

        subj = str(meta.get("subject_code") or "").lower()
        if subj != subject_code.lower():
            continue
        if topic_group is not None:
            tg = str(meta.get("topic_group") or "").lower()
            if tg != topic_group.lower():
                continue
        if str(row.id) in seen:
            continue
        if not row.answer_json or not _question_has_correct_option(row):
            continue
        seen.add(str(row.id))
        chosen.append(
            PracticeQuestionRef(
                question_id=str(row.id),
                subject_code=subject_code,
                topic_group=topic_group,
                independently_validated=True,
                solver_audit_id=str(meta.get("day6_solver_evidence_id") or ""),
                metadata_json={
                    "persisted_selection": True,
                    "labeled_test_fixture": True,
                    "day6_validation_audit_id": run_id,
                    "synthetic_fixture_only": True,
                },
            )
        )
        if len(chosen) >= requested_count:
            break

    if len(chosen) < requested_count:
        return (
            chosen,
            [AdvancedIssueCode.COUNT_SHORTAGE],
            AdvancedPlanVerdict.SHORTAGE,
        )
    if blocking_issues:
        return chosen, blocking_issues, AdvancedPlanVerdict.FAIL
    if topic_group and topic_group.lower() != EDUVIJNA_DERIVED_TOPIC_GROUP:
        return chosen, [AdvancedIssueCode.WRONG_TOPIC], AdvancedPlanVerdict.FAIL
    return chosen, [], AdvancedPlanVerdict.PASS