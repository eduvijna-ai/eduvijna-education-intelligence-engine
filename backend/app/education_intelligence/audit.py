from __future__ import annotations

from sqlalchemy.orm import Session

from app.education_intelligence.contracts import ValidationRunSummary
from app.models.education_intelligence import ValidationAuditRun


def persist_validation_run(
    session: Session,
    summary: ValidationRunSummary,
    *,
    institution_id: str | None = None,
    actor_id: str | None = None,
) -> ValidationAuditRun:
    record = ValidationAuditRun(
        run_id=summary.run_id,
        input_hash=summary.input_hash,
        taxonomy_version=summary.taxonomy_version,
        policy_version=summary.policy_version,
        aggregate_status=summary.aggregate_status.value,
        blocking_failure=summary.blocking_failure,
        institution_id=institution_id,
        actor_id=actor_id,
        results_json=[r.model_dump(mode="json") for r in summary.results],
        metadata_json={"validator_versions": summary.validator_versions},
    )
    session.add(record)
    session.flush()
    return record
