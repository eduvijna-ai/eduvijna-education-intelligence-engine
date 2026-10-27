from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import PaperDistributionRequest, PaperDistributionResult
from app.paper_distribution.execution_context import PaperExecutionContext
from app.prerequisite_intelligence.stable_ids import stable_digest

PAPER_POLICY_VERSION = "paper-distribution@v1"
PAPER_AUDIT_KIND = "paper_distribution"


def _paper_audit_run_id(institution_id: str | None, fingerprint: str) -> str:
    return stable_digest("paper-dist", institution_id or "global", fingerprint)[:64]


def persist_paper_distribution_audit(
    session: Session,
    request: PaperDistributionRequest,
    result: PaperDistributionResult,
    *,
    execution_context: PaperExecutionContext | None = None,
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
    day6_validation_run_id: str | None = None,
) -> str:
    fingerprint = result.result_fingerprint or ""
    if not fingerprint:
        raise ValueError("result_fingerprint required for paper audit persistence")

    if execution_mode == TrustExecutionMode.PRODUCTION and execution_context is None:
        raise ValueError("execution_context required for production paper audit persistence")

    institution_id = execution_context.institution_id if execution_context else None
    actor_id = execution_context.actor_id if execution_context else None
    if execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE:
        institution_id = institution_id or (request.metadata_json or {}).get("institution_id")
        actor_id = actor_id or (request.metadata_json or {}).get("actor_id")

    policy_version = request.target_policy_version or PAPER_POLICY_VERSION
    item_ids = sorted({item.item_id for item in request.items})

    candidates = session.scalars(
        select(ValidationAuditRun).where(
            and_(
                ValidationAuditRun.input_hash == fingerprint,
                ValidationAuditRun.policy_version == policy_version,
                ValidationAuditRun.institution_id == institution_id,
            )
        )
    ).all()
    for candidate in candidates:
        meta = candidate.metadata_json or {}
        if meta.get("kind") != PAPER_AUDIT_KIND:
            continue
        if meta.get("day6_validation_run_id") != day6_validation_run_id:
            continue
        if sorted(meta.get("validated_item_ids") or []) != item_ids:
            continue
        return str(candidate.id)

    record = ValidationAuditRun(
        run_id=_paper_audit_run_id(institution_id, fingerprint),
        input_hash=fingerprint,
        taxonomy_version=request.taxonomy_version,
        policy_version=policy_version,
        aggregate_status=result.verdict.value,
        blocking_failure=result.verdict.value == "fail",
        institution_id=institution_id,
        actor_id=actor_id,
        results_json=[
            {
                "paper_id": result.paper_id,
                "verdict": result.verdict.value,
                "item_count": result.item_count,
                "issue_codes": [code.value for code in result.issue_codes],
            }
        ],
        metadata_json={
            "kind": PAPER_AUDIT_KIND,
            "paper_id": request.paper_id,
            "requested_count": request.requested_count,
            "result_fingerprint": fingerprint,
            "target_policy_version": request.target_policy_version,
            "day6_validation_run_id": day6_validation_run_id,
            "validated_item_ids": item_ids,
        },
    )
    session.add(record)
    session.flush()
    return str(record.id)
