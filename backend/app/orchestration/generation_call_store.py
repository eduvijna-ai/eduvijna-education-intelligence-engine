from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationGenerationCall
from app.orchestration.control_session import commit_control
from app.orchestration.gateway.types import GenerationResponse

GenerationCallStatus = Literal["started", "completed", "ambiguous", "invalid"]


def _record(
    session: Session, *, run_id: str, cache_key: str
) -> OrchestrationGenerationCall | None:
    return session.scalar(
        select(OrchestrationGenerationCall).where(
            OrchestrationGenerationCall.run_id == run_id,
            OrchestrationGenerationCall.cache_key == cache_key,
        )
    )


def load_persisted_call(
    session: Session, *, run_id: str, cache_key: str
) -> GenerationResponse | None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is None or record.status != "completed" or not record.response_json:
        return None
    raw = record.response_json
    return GenerationResponse(
        parsed=raw["parsed"],
        raw_text="",
        latency_ms=float(raw.get("latency_ms", 0)),
        gateway_request_id=raw.get("gateway_request_id"),
        usage=dict(raw.get("usage") or {}),
    )


def load_call_status(session: Session, *, run_id: str, cache_key: str) -> str | None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    return record.status if record is not None else None


def claim_generation_call_start(
    session: Session, *, run_id: str, cache_key: str, commit: bool = True
) -> bool:
    """Return True when this caller owns a new in-flight claim."""
    existing = _record(session, run_id=run_id, cache_key=cache_key)
    if existing is not None:
        return False
    try:
        with session.begin_nested():
            session.add(
                OrchestrationGenerationCall(
                    run_id=run_id,
                    cache_key=cache_key,
                    status="started",
                    response_json=None,
                )
            )
            session.flush()
    except IntegrityError:
        return False
    if commit:
        commit_control(session)
    return True


def abandon_generation_call(
    session: Session, *, run_id: str, cache_key: str, commit: bool = True
) -> None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is not None and record.status == "started":
        session.delete(record)
        session.flush()
    if commit:
        commit_control(session)


def authorize_generation_call_retry(
    session: Session, *, run_id: str, cache_key: str, commit: bool = True
) -> bool:
    """Explicitly transition a started/ambiguous call into one authorized retry attempt."""
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is None or record.status not in {"started", "ambiguous"}:
        return False
    record.status = "started"
    record.response_json = None
    session.flush()
    if commit:
        commit_control(session)
    return True


def mark_generation_call_ambiguous(
    session: Session, *, run_id: str, cache_key: str, commit: bool = True
) -> None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is None:
        return
    record.status = "ambiguous"
    record.response_json = None
    session.flush()
    if commit:
        commit_control(session)


def complete_generation_call(
    session: Session,
    *,
    run_id: str,
    cache_key: str,
    structured_payload: dict[str, Any],
    latency_ms: float,
    gateway_request_id: str | None,
    usage: dict[str, Any],
    commit: bool = True,
) -> None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is None:
        record = OrchestrationGenerationCall(
            run_id=run_id,
            cache_key=cache_key,
            status="completed",
        )
        session.add(record)
    record.status = "completed"
    record.response_json = {
        "parsed": structured_payload,
        "latency_ms": latency_ms,
        "gateway_request_id": gateway_request_id,
        "usage": usage,
    }
    session.flush()
    if commit:
        commit_control(session)


def mark_generation_call_invalid(
    session: Session, *, run_id: str, cache_key: str, commit: bool = True
) -> None:
    record = _record(session, run_id=run_id, cache_key=cache_key)
    if record is None:
        return
    record.status = "invalid"
    record.response_json = None
    session.flush()
    if commit:
        commit_control(session)


def clear_started_calls_for_run(session: Session, *, run_id: str, commit: bool = True) -> None:
    session.execute(
        delete(OrchestrationGenerationCall).where(
            OrchestrationGenerationCall.run_id == run_id,
            OrchestrationGenerationCall.status == "started",
        )
    )
    session.flush()
    if commit:
        commit_control(session)
