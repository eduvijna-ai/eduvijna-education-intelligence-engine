from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationIdempotencyRecord
from app.orchestration.contracts import OrchestrationRequest, OrchestrationResult
from app.orchestration.exceptions import IdempotencyConflictError


def load_completed_result(
    session: Session, request: OrchestrationRequest
) -> OrchestrationResult | None:
    record = session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    if record is None:
        return None
    if record.request_hash != request.request_hash():
        raise IdempotencyConflictError(request.idempotency_key)
    if record.status != "completed":
        return None
    return OrchestrationResult.model_validate(record.result_json)


def claim_idempotency(
    session: Session, request: OrchestrationRequest
) -> tuple[OrchestrationResult | None, str]:
    """Reserve idempotency key before gateway calls. Returns (completed_result, run_id)."""
    existing = session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    request_hash = request.request_hash()
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError(request.idempotency_key)
        if existing.status == "completed":
            return OrchestrationResult.model_validate(existing.result_json), existing.run_id
        return None, existing.run_id

    record = OrchestrationIdempotencyRecord(
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        run_id=request.run_id,
        status="in_progress",
        result_json={},
        completed_at=None,
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raced = session.scalar(
            select(OrchestrationIdempotencyRecord).where(
                OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
            )
        )
        if raced is None:
            raise
        if raced.request_hash != request_hash:
            raise IdempotencyConflictError(request.idempotency_key) from None
        if raced.status == "completed":
            return OrchestrationResult.model_validate(raced.result_json), raced.run_id
        return None, raced.run_id
    return None, request.run_id


def store_completed_result(
    session: Session, request: OrchestrationRequest, result: OrchestrationResult
) -> OrchestrationIdempotencyRecord:
    existing = session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == request.idempotency_key
        )
    )
    if existing is None:
        raise IdempotencyConflictError(request.idempotency_key, "missing_idempotency_claim")
    if existing.request_hash != request.request_hash():
        raise IdempotencyConflictError(request.idempotency_key)
    payload = result.model_dump(mode="json")
    existing.run_id = result.run_id
    existing.status = "completed"
    existing.result_json = payload
    existing.completed_at = datetime.now(UTC)
    return existing
