from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import PaperDistributionRequest, PaperDistributionResult
from app.paper_distribution.execution_context import PaperExecutionContext

PAPER_POLICY_VERSION = "paper-distribution@v1"
PAPER_AUDIT_KIND = "paper_distribution"


def persist_paper_distribution_audit(
    session: Session,
    request: PaperDistributionRequest,
    result: PaperDistributionResult,
    *,
    execution_context: PaperExecutionContext | None = None,
) -> str:
    fingerprint = result.result_fingerprint or ""
    if not fingerprint:
        raise ValueError("result_fingerprint required for paper audit persistence")

    institution_id = (
        execution_context.institution_id if execution_context else None
    ) or (request.metadata_json or {}).get("institution_id")
    actor_id = (
        execution_context.actor_id if execution_context else None
    ) or (request.metadata_json or {}).get("actor_id")
    policy_version = request.target_policy_version or PAPER_POLICY_VERSION

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
        if (candidate.metadata_json or {}).get("kind") == PAPER_AUDIT_KIND:
            return str(candidate.id)

    tenant_key = institution_id or "global"
    record = ValidationAuditRun(
        run_id=f"paper-dist-{tenant_key}-{fingerprint[:32]}",
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
        },
    )
    session.add(record)
    session.flush()
    return str(record.id)
