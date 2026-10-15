from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orchestration import OrchestrationCheckpointLease
from app.orchestration.control_session import commit_control


class LeaseAcquireResult(StrEnum):
    ACQUIRED = "acquired"
    BLOCKED = "blocked"
    STALE_RECLAIMED = "stale_reclaimed"


def _stale_seconds() -> int:
    raw = os.environ.get("EDUVIJNA_ORCHESTRATION_LEASE_STALE_SECONDS", "3600").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 3600


def _is_stale(lease: OrchestrationCheckpointLease) -> bool:
    updated = lease.updated_at
    if updated is None:
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated > timedelta(seconds=_stale_seconds())


def try_acquire_execution_lease(
    session: Session,
    *,
    thread_id: str,
    run_id: str,
    holder_id: str,
) -> LeaseAcquireResult:
    existing = session.scalar(
        select(OrchestrationCheckpointLease).where(
            OrchestrationCheckpointLease.thread_id == thread_id
        )
    )
    if existing is not None:
        if existing.holder_id == holder_id:
            existing.run_id = run_id
            session.flush()
            return LeaseAcquireResult.ACQUIRED
        if not _is_stale(existing):
            return LeaseAcquireResult.BLOCKED
        session.delete(existing)
        session.flush()

    lease = OrchestrationCheckpointLease(
        thread_id=thread_id,
        run_id=run_id,
        holder_id=holder_id,
        notes=None,
    )
    try:
        with session.begin_nested():
            session.add(lease)
            session.flush()
    except IntegrityError:
        raced = session.scalar(
            select(OrchestrationCheckpointLease).where(
                OrchestrationCheckpointLease.thread_id == thread_id
            )
        )
        if raced is None:
            raise
        if raced.holder_id == holder_id:
            return LeaseAcquireResult.ACQUIRED
        if _is_stale(raced):
            session.delete(raced)
            session.flush()
            session.add(
                OrchestrationCheckpointLease(
                    thread_id=thread_id,
                    run_id=run_id,
                    holder_id=holder_id,
                )
            )
            session.flush()
            return LeaseAcquireResult.STALE_RECLAIMED
        return LeaseAcquireResult.BLOCKED
    return LeaseAcquireResult.ACQUIRED


def release_execution_lease(
    session: Session, *, thread_id: str, holder_id: str, commit: bool = True
) -> None:
    existing = session.scalar(
        select(OrchestrationCheckpointLease).where(
            OrchestrationCheckpointLease.thread_id == thread_id,
            OrchestrationCheckpointLease.holder_id == holder_id,
        )
    )
    if existing is not None:
        session.delete(existing)
        session.flush()
    if commit:
        commit_control(session)
