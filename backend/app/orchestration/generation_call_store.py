from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationGenerationCall
from app.orchestration.gateway.types import GenerationResponse


def load_persisted_call(
    session: Session, *, run_id: str, cache_key: str
) -> GenerationResponse | None:
    record = session.scalar(
        select(OrchestrationGenerationCall).where(
            OrchestrationGenerationCall.run_id == run_id,
            OrchestrationGenerationCall.cache_key == cache_key,
        )
    )
    if record is None:
        return None
    raw = record.response_json
    return GenerationResponse(
        parsed=raw["parsed"],
        raw_text=raw["raw_text"],
        latency_ms=float(raw.get("latency_ms", 0)),
        gateway_request_id=raw.get("gateway_request_id"),
        usage=dict(raw.get("usage") or {}),
    )


def persist_generation_call(
    session: Session,
    *,
    run_id: str,
    cache_key: str,
    response: GenerationResponse,
    commit: bool = True,
) -> None:
    if load_persisted_call(session, run_id=run_id, cache_key=cache_key) is not None:
        return
    payload = {
        "parsed": response.parsed,
        "raw_text": response.raw_text,
        "latency_ms": response.latency_ms,
        "gateway_request_id": response.gateway_request_id,
        "usage": response.usage,
    }
    try:
        with session.begin_nested():
            session.add(
                OrchestrationGenerationCall(
                    run_id=run_id,
                    cache_key=cache_key,
                    response_json=payload,
                )
            )
            session.flush()
    except IntegrityError:
        return
    if commit:
        session.commit()
