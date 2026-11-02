from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import ValidationAuditRun
from app.orchestration.contracts import ResolvedScope

_ACCEPTED_DAY6_STATUSES = {"pass", "accepted", "ok", "success"}


def find_accepted_day6_audit_run(
    session: Session,
    *,
    item_id: str,
    input_hash: str,
    scope: ResolvedScope,
) -> ValidationAuditRun | None:
    """Return a persisted non-blocking Day6 run matching canonical input hash and scope."""
    if not input_hash:
        return None
    records = session.scalars(
        select(ValidationAuditRun).where(
            ValidationAuditRun.input_hash == input_hash,
            ValidationAuditRun.blocking_failure.is_(False),
        )
    ).all()
    for record in records:
        aggregate = str(record.aggregate_status or "").lower()
        if aggregate not in _ACCEPTED_DAY6_STATUSES:
            continue
        validated_items = (record.metadata_json or {}).get("validated_items") or []
        item_entry = next(
            (entry for entry in validated_items if str(entry.get("item_id")) == item_id),
            None,
        )
        if item_entry is None:
            continue
        if str(item_entry.get("input_hash") or "") != str(input_hash):
            continue
        run_scope = (record.metadata_json or {}).get("scope") or {}
        if scope.organization_id and str(run_scope.get("organization_id") or "") != str(
            scope.organization_id
        ):
            continue
        if scope.institution_id and str(run_scope.get("institution_id") or "") != str(
            scope.institution_id
        ):
            continue
        if scope.curriculum_version_id and str(
            run_scope.get("curriculum_version_id") or ""
        ) != str(scope.curriculum_version_id):
            continue
        return record
    return None


def day6_summary_from_audit_run(
    record: ValidationAuditRun,
) -> tuple[str, str, list[str], list[str]]:
    validated_items = (record.metadata_json or {}).get("validated_items") or []
    first = validated_items[0] if validated_items and isinstance(validated_items[0], dict) else {}
    learning_outcome_ids = list(first.get("learning_outcome_ids") or [])
    competency_codes = list(first.get("competency_codes") or [])
    return str(record.id), str(record.input_hash), learning_outcome_ids, competency_codes
