from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.platform_jobs import DurableAsyncJob
from app.platform.auth.principal import RequestPrincipal
from app.platform.capability_registry import assert_capability_ready, get_capability
from app.platform.errors import CapabilityNotReadyError, ConflictError, NotFoundError
from app.platform.jobs.enums import LEGAL_TRANSITIONS, TERMINAL_STATUSES, JobStatus

LEASE_SECONDS = 60


def request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def enqueue_job(
    session: Session,
    *,
    principal: RequestPrincipal,
    capability_code: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    synthetic_fixture_only: bool = False,
) -> DurableAsyncJob:
    if not synthetic_fixture_only:
        assert_capability_ready(capability_code)
    elif capability_code != "platform.synthetic_echo":
        raise CapabilityNotReadyError(
            capability=capability_code,
            reason="Synthetic jobs allowed only for platform.synthetic_echo fixture",
        )

    fingerprint = request_fingerprint(request_payload)
    existing = session.scalar(
        select(DurableAsyncJob).where(
            DurableAsyncJob.organization_id == principal.organization_id,
            DurableAsyncJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("Idempotency key reused with different payload")
        return existing

    job = DurableAsyncJob(
        id=uuid.uuid4().hex,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        principal_id=principal.principal_id,
        api_key_id=principal.actor_ref if principal.auth_method == "api_key" else None,
        actor_kind=principal.actor_kind,
        actor_ref=principal.actor_ref,
        capability_code=capability_code,
        status=JobStatus.QUEUED.value,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        request_json=request_payload,
        synthetic_fixture_only=synthetic_fixture_only,
    )
    session.add(job)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        replay = session.scalar(
            select(DurableAsyncJob).where(
                DurableAsyncJob.organization_id == principal.organization_id,
                DurableAsyncJob.idempotency_key == idempotency_key,
            )
        )
        if replay is None:
            raise exc
        if replay.request_fingerprint != fingerprint:
            raise ConflictError("Idempotency key reused with different payload") from exc
        return replay
    return job


def get_job_for_principal(
    session: Session, *, principal: RequestPrincipal, job_id: str
) -> DurableAsyncJob:
    job = session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == job_id))
    if job is None:
        raise NotFoundError("Job not found")
    if job.organization_id != principal.organization_id:
        raise NotFoundError("Job not found")
    if (
        job.institution_id
        and principal.institution_id
        and job.institution_id != principal.institution_id
    ):
        raise NotFoundError("Job not found")
    return job


def cancel_job(session: Session, *, principal: RequestPrincipal, job_id: str) -> DurableAsyncJob:
    job = get_job_for_principal(session, principal=principal, job_id=job_id)
    if job.status in {s.value for s in TERMINAL_STATUSES}:
        return job
    job.status = JobStatus.CANCELED.value
    job.canceled_at = datetime.now(UTC)
    job.lease_holder = None
    job.lease_expires_at = None
    return job


def claim_next_job(session: Session, *, worker_id: str) -> DurableAsyncJob | None:
    now = datetime.now(UTC)
    # recover expired leases
    if True:
        expired = session.scalars(
            select(DurableAsyncJob)
            .where(
                DurableAsyncJob.lease_expires_at.is_not(None),
                DurableAsyncJob.lease_expires_at < now,
                DurableAsyncJob.status.not_in([s.value for s in TERMINAL_STATUSES]),
            )
            .limit(5)
        ).all()
        for job in expired:
            job.lease_holder = None
            job.lease_expires_at = None
            if job.status not in {s.value for s in TERMINAL_STATUSES}:
                job.status = JobStatus.QUEUED.value
        session.flush()

    candidate = session.scalars(
        select(DurableAsyncJob)
        .where(DurableAsyncJob.status == JobStatus.QUEUED.value)
        .order_by(DurableAsyncJob.created_at)
        .limit(1)
        .with_for_update()
    ).first()
    if candidate is None:
        return None
    candidate.lease_holder = worker_id
    candidate.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    candidate.lease_fence += 1
    candidate.attempts += 1
    candidate.status = JobStatus.PLANNING.value
    session.flush()
    return candidate


def transition_job(session: Session, job: DurableAsyncJob, new_status: JobStatus) -> None:
    current = JobStatus(job.status)
    if new_status not in LEGAL_TRANSITIONS[current]:
        raise ConflictError(f"Illegal transition {current.value} -> {new_status.value}")
    job.status = new_status.value
    if new_status in TERMINAL_STATUSES:
        job.completed_at = datetime.now(UTC)
        job.lease_holder = None
        job.lease_expires_at = None


def complete_synthetic_job(session: Session, job: DurableAsyncJob) -> None:
    if not job.synthetic_fixture_only:
        raise CapabilityNotReadyError(
            capability=job.capability_code,
            reason="Non-synthetic jobs cannot complete without accepted readiness",
        )
    transition_job(session, job, JobStatus.COMPLETED)
    job.result_json = {
        "synthetic": True,
        "echo": job.request_json,
        "academic_readiness": False,
        "note": "Synthetic fixture only — not academic readiness",
    }


def try_enqueue_generation(
    session: Session,
    *,
    principal: RequestPrincipal,
    capability_code: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
) -> DurableAsyncJob | None:
    record = get_capability(capability_code)
    if record is None:
        raise CapabilityNotReadyError(capability=capability_code, reason="Unknown capability")
    try:
        assert_capability_ready(capability_code)
    except CapabilityNotReadyError:
        return None
    return enqueue_job(
        session,
        principal=principal,
        capability_code=capability_code,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )
