from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationIdempotencyRecord
from app.orchestration.contracts import OrchestrationRequest, OrchestrationResult
from app.orchestration.exceptions import IdempotencyConflictError

IdempotencyStatus = Literal["in_progress", "completed", "failed"]


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


def _load_record(session: Session, idempotency_key: str) -> OrchestrationIdempotencyRecord | None:
    return session.scalar(
        select(OrchestrationIdempotencyRecord).where(
            OrchestrationIdempotencyRecord.idempotency_key == idempotency_key
        )
    )


def claim_idempotency(
    session: Session, request: OrchestrationRequest
) -> tuple[OrchestrationResult | None, str, IdempotencyStatus | None]:
    """Reserve idempotency key before gateway calls.

    Returns (terminal_result_if_any, canonical_run_id, record_status).
    Caller must commit immediately after claim before model side effects.
    """
    request_hash = request.request_hash()
    existing = _load_record(session, request.idempotency_key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError(request.idempotency_key)
        if existing.status == "completed":
            return (
                OrchestrationResult.model_validate(existing.result_json),
                existing.run_id,
                "completed",
            )
        if existing.status == "failed":
            return (
                OrchestrationResult.model_validate(existing.result_json),
                existing.run_id,
                "failed",
            )
        return None, existing.run_id, "in_progress"

    try:
        with session.begin_nested():
            session.add(
                OrchestrationIdempotencyRecord(
                    idempotency_key=request.idempotency_key,
                    request_hash=request_hash,
                    run_id=request.run_id,
                    status="in_progress",
                    result_json={},
                    completed_at=None,
                )
            )
            session.flush()
    except IntegrityError:
        raced = _load_record(session, request.idempotency_key)
        if raced is None:
            raise
        if raced.request_hash != request_hash:
            raise IdempotencyConflictError(request.idempotency_key) from None
        if raced.status == "completed":
            return (
                OrchestrationResult.model_validate(raced.result_json),
                raced.run_id,
                "completed",
            )
        if raced.status == "failed":
            return (
                OrchestrationResult.model_validate(raced.result_json),
                raced.run_id,
                "failed",
            )
        return None, raced.run_id, "in_progress"
    return None, request.run_id, "in_progress"


def store_terminal_result(
    session: Session,
    request: OrchestrationRequest,
    result: OrchestrationResult,
    *,
    status: IdempotencyStatus,
) -> OrchestrationIdempotencyRecord:
    existing = _load_record(session, request.idempotency_key)
    if existing is None:
        raise IdempotencyConflictError(request.idempotency_key, "missing_idempotency_claim")
    if existing.request_hash != request.request_hash():
        raise IdempotencyConflictError(request.idempotency_key)
    payload = result.model_dump(mode="json")
    existing.run_id = result.run_id
    existing.status = status
    existing.result_json = payload
    existing.completed_at = datetime.now(UTC)
    return existing


def store_completed_result(
    session: Session, request: OrchestrationRequest, result: OrchestrationResult
) -> OrchestrationIdempotencyRecord:
    return store_terminal_result(session, request, result, status="completed")
