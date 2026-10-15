from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationIdempotencyRecord
from app.orchestration.contracts import OrchestrationRequest, OrchestrationResult


def load_completed_result(
    session: Session, request: OrchestrationRequest
) -> OrchestrationResult | None:
    record = session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    if record is None or record.status != "completed":
        return None
    if record.request_hash != request.request_hash():
        return None
    return OrchestrationResult.model_validate(record.result_json)


def store_completed_result(
    session: Session, request: OrchestrationRequest, result: OrchestrationResult
) -> OrchestrationIdempotencyRecord:
    existing = session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    payload = result.model_dump(mode="json")
    if existing is None:
        record = OrchestrationIdempotencyRecord(
            idempotency_key=request.idempotency_key,
            request_hash=request.request_hash(),
            run_id=result.run_id,
            status="completed",
            result_json=payload,
            completed_at=datetime.now(UTC),
        )
        session.add(record)
        return record
    existing.request_hash = request.request_hash()
    existing.run_id = result.run_id
    existing.status = "completed"
    existing.result_json = payload
    existing.completed_at = datetime.now(UTC)
    return existing
