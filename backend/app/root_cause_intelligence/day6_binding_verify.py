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
    if not validation_run_id:
        return False
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.id == validation_run_id)
    ).first()
    if record is None or record.blocking_failure:
        return False
    aggregate = str(record.aggregate_status or "").lower()
    if aggregate not in {"pass", "accepted", "ok", "success"}:
        return False
    validated_items = (record.metadata_json or {}).get("validated_items") or []
    item_entry = next(
        (entry for entry in validated_items if str(entry.get("item_id")) == item_id),
        None,
    )
    if item_entry is None:
        return False
    if input_hash and str(item_entry.get("input_hash") or "") != input_hash:
        return False
    if learning_outcome_ids:
        persisted_lo = item_entry.get("learning_outcome_id") or item_entry.get(
            "declared_learning_outcome_id"
        )
        if persisted_lo and str(persisted_lo) not in {str(lo) for lo in learning_outcome_ids}:
            return False
    if competency_codes:
        persisted_codes = {
            str(code) for code in (item_entry.get("competency_codes") or []) if code
        }
        if persisted_codes and not persisted_codes.intersection(set(competency_codes)):
            return False
    return True
