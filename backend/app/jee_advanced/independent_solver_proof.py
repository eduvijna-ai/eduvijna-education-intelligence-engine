"""Shared Day6 independent-solver proof reused by practice and verification (D12-AC-F01)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.enums import ValidationStatus
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.models import Question, ValidationAuditRun


def solver_evidence_proven(
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


def validation_run_covers_question(
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
    scope_org = str(scope.get("organization_id") or meta.get("organization_id") or "").strip()
    if not scope_org:
        return False, "validation_record_org_missing"
    if scope_org != organization_id.strip():
        return False, "validation_org_mismatch"
    if institution_id is not None:
        scope_inst = str(
            scope.get("institution_id") or record.institution_id or ""
        ).strip()
        if not scope_inst:
            return False, "validation_record_institution_missing"
        if scope_inst != institution_id.strip():
            return False, "validation_institution_mismatch"

    solver_id = str((question.metadata_json or {}).get("day6_solver_evidence_id") or "")
    if not solver_evidence_proven(record, question_id=str(question.id), solver_id=solver_id):
        return False, "independent_solver_not_persisted"

    return True, None