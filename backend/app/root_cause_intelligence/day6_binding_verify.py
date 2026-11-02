from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import ValidationAuditRun


def day6_binding_matches_persisted_run(
    session: Session,
    *,
    item_id: str,
    validation_run_id: str | None,
    input_hash: str | None,
    learning_outcome_ids: list[str],
    competency_codes: list[str],
) -> bool:
    ok, _ = verify_production_day6_binding(
        session,
        item_id=item_id,
        validation_run_id=validation_run_id,
        input_hash=input_hash,
        learning_outcome_ids=learning_outcome_ids,
        competency_codes=competency_codes,
    )
    return ok


def verify_production_day6_binding(
    session: Session,
    *,
    item_id: str,
    validation_run_id: str | None,
    input_hash: str | None,
    learning_outcome_ids: list[str],
    competency_codes: list[str],
    organization_id: str | None = None,
    institution_id: str | None = None,
    curriculum_version_id: str | None = None,
    grade_year_code: str | None = None,
    medium_code: str | None = None,
    subject_code: str | None = None,
) -> tuple[bool, str | None]:
    if not validation_run_id:
        return False, "day6_validation_run_id"
    if not input_hash:
        return False, "day6_input_hash"
    if not learning_outcome_ids:
        return False, "learning_outcome_ids"
    if not competency_codes:
        return False, "competency_codes"
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.id == validation_run_id)
    ).first()
    if record is None or record.blocking_failure:
        return False, "day6_validation_run_id"
    aggregate = str(record.aggregate_status or "").lower()
    if aggregate not in {"pass", "accepted", "ok", "success"}:
        return False, "day6_validation_run_id"
    validated_items = (record.metadata_json or {}).get("validated_items") or []
    item_entry = next(
        (entry for entry in validated_items if str(entry.get("item_id")) == item_id),
        None,
    )
    if item_entry is None:
        return False, "day6_binding.item_id"
    if str(item_entry.get("input_hash") or "") != str(input_hash):
        return False, "day6_input_hash"
    persisted_los: set[str] = set()
    raw_los = item_entry.get("learning_outcome_ids")
    if isinstance(raw_los, list):
        persisted_los = {str(lo) for lo in raw_los if lo}
    if not persisted_los:
        persisted_lo = item_entry.get("learning_outcome_id") or item_entry.get(
            "declared_learning_outcome_id"
        )
        if persisted_lo:
            persisted_los = {str(persisted_lo)}
    if not persisted_los:
        return False, "learning_outcome_ids"
    requested_lo = {str(lo) for lo in learning_outcome_ids if lo}
    if persisted_los != requested_lo:
        return False, "learning_outcome_ids"
    persisted_codes = {
        str(code) for code in (item_entry.get("competency_codes") or []) if code
    }
    if not persisted_codes:
        return False, "competency_codes"
    requested_codes = {str(code) for code in competency_codes if code}
    if persisted_codes != requested_codes:
        return False, "competency_codes"
    run_scope = (record.metadata_json or {}).get("scope") or {}
    if organization_id:
        if str(run_scope.get("organization_id") or "") != str(organization_id):
            return False, "organization_id"
    if institution_id:
        if str(run_scope.get("institution_id") or "") != str(institution_id):
            return False, "institution_id"
    if curriculum_version_id:
        if str(run_scope.get("curriculum_version_id") or "") != str(curriculum_version_id):
            return False, "curriculum_version_id"
    for field, expected, path in (
        ("grade_year_code", grade_year_code, "grade_year_code"),
        ("medium_code", medium_code, "medium_code"),
        ("subject_code", subject_code, "subject_code"),
    ):
        if expected:
            persisted = item_entry.get(field)
            if not persisted:
                return False, path
            if str(persisted) != str(expected):
                return False, path
    return True, None
