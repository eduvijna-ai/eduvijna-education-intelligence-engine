from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import PaperDistributionRequest, PaperDistributionResult

PAPER_POLICY_VERSION = "paper-distribution@v1"


def persist_paper_distribution_audit(
    session: Session,
    request: PaperDistributionRequest,
    result: PaperDistributionResult,
) -> str:
    fingerprint = result.result_fingerprint or ""
    if not fingerprint:
        raise ValueError("result_fingerprint required for paper audit persistence")

    existing = session.scalar(
        select(ValidationAuditRun).where(ValidationAuditRun.input_hash == fingerprint)
    )
    if existing is not None:
        return str(existing.id)

    record = ValidationAuditRun(
        run_id=f"paper-dist-{fingerprint[:40]}",
        input_hash=fingerprint,
        taxonomy_version=request.taxonomy_version,
        policy_version=PAPER_POLICY_VERSION,
        aggregate_status=result.verdict.value,
        blocking_failure=result.verdict.value == "fail",
        results_json=[
            {
                "paper_id": result.paper_id,
                "verdict": result.verdict.value,
                "item_count": result.item_count,
                "issue_codes": [code.value for code in result.issue_codes],
            }
        ],
        metadata_json={
            "kind": "paper_distribution",
            "paper_id": request.paper_id,
            "requested_count": request.requested_count,
            "result_fingerprint": fingerprint,
        },
    )
    session.add(record)
    session.flush()
    return str(record.id)
