from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.platform_jobs import DurableAsyncJob
from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.capability_registry import assert_capability_ready, get_capability
from app.platform.errors import CapabilityNotReadyError, ConflictError, NotFoundError
from app.platform.ids import canonical_id
from app.platform.jobs.enums import LEGAL_TRANSITIONS, TERMINAL_STATUSES, JobStatus
from app.platform.jobs.synthetic import SYNTHETIC_INTERNAL_REQUEST, SYNTHETIC_JOB_CAPABILITY

LEASE_SECONDS = 60


def _cas_job_status(
    session: Session,
    *,
    job_id: str,
    expected_status: str,
    new_status: str,
    lease_holder: str | None = None,
    lease_fence: int | None = None,
    lease_expires_at: datetime | None = None,
    clear_lease: bool = False,
    canceled_at: datetime | None = None,
    completed_at: datetime | None = None,
    result_json: dict[str, Any] | None = None,
    error_code: str | None = None,
    worker_id: str | None = None,
    require_fence: int | None = None,
) -> int:
    values: dict[str, Any] = {"status": new_status}
    if lease_holder is not None:
        values["lease_holder"] = lease_holder
    if lease_fence is not None:
        values["lease_fence"] = lease_fence
    if lease_expires_at is not None:
        values["lease_expires_at"] = lease_expires_at
    if clear_lease:
        values["lease_holder"] = None
        values["lease_expires_at"] = None
    if canceled_at is not None:
        values["canceled_at"] = canceled_at
    if completed_at is not None:
        values["completed_at"] = completed_at
    if result_json is not None:
        values["result_json"] = result_json
    if error_code is not None:
        values["error_code"] = error_code
    conditions = [
        DurableAsyncJob.id == job_id,
        DurableAsyncJob.status == expected_status,
    ]
    if worker_id is not None:
        conditions.append(DurableAsyncJob.lease_holder == worker_id)
    if require_fence is not None:
        conditions.append(DurableAsyncJob.lease_fence == require_fence)
    result = session.execute(update(DurableAsyncJob).where(*conditions).values(**values))
    count = int(getattr(result, "rowcount", 0) or 0)
    session.flush()
    return count


def idempotency_scope_key(
    *,
    principal: RequestPrincipal,
    capability_code: str,
    idempotency_key: str,
) -> str:
    institution = principal.institution_id or ""
    material = "|".join(
        (
            principal.organization_id,
            institution,
            principal.principal_id,
            principal.actor_kind,
            principal.actor_ref,
            capability_code,
            idempotency_key,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def request_fingerprint(
    *,
    capability_code: str,
    principal: RequestPrincipal,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "capability_code": capability_code,
            "principal_id": principal.principal_id,
            "actor_ref": principal.actor_ref,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _assert_job_owner(job: DurableAsyncJob, principal: RequestPrincipal, *, cancel: bool) -> None:
    permission = "jobs:cancel" if cancel else "jobs:read"
    require_permission(principal.scopes, permission)
    if job.organization_id != principal.organization_id:
        raise NotFoundError("Job not found")
    if job.institution_id != principal.institution_id:
        raise NotFoundError("Job not found")
    if principal.auth_method == "api_key":
        if job.api_key_id != principal.actor_ref:
            raise NotFoundError("Job not found")
        return
    if job.principal_id != principal.principal_id:
        raise NotFoundError("Job not found")


def enqueue_job(
    session: Session,
    *,
    principal: RequestPrincipal,
    capability_code: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    synthetic_fixture_only: bool = False,
) -> DurableAsyncJob:
    require_permission(principal.scopes, "jobs:submit")
    if synthetic_fixture_only:
        payload_ok = request_payload == SYNTHETIC_INTERNAL_REQUEST
        if not payload_ok or capability_code != SYNTHETIC_JOB_CAPABILITY:
            raise CapabilityNotReadyError(
                capability=capability_code,
                reason="Synthetic enqueue is internal-harness only",
            )
    else:
        assert_capability_ready(capability_code)

    scope_key = idempotency_scope_key(
        principal=principal,
        capability_code=capability_code,
        idempotency_key=idempotency_key,
    )
    fingerprint = request_fingerprint(
        capability_code=capability_code,
        principal=principal,
        payload=request_payload,
    )
    existing = session.scalar(
        select(DurableAsyncJob).where(
            DurableAsyncJob.organization_id == principal.organization_id,
            DurableAsyncJob.idempotency_scope_key == scope_key,
        )
    )
    if existing is not None:
        _assert_job_owner(existing, principal, cancel=False)
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("Idempotency key reused with different payload or operation")
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
        idempotency_scope_key=scope_key,
        request_fingerprint=fingerprint,
        request_json=dict(request_payload),
        synthetic_fixture_only=synthetic_fixture_only,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:
        replay = session.scalar(
            select(DurableAsyncJob).where(
                DurableAsyncJob.organization_id == principal.organization_id,
                DurableAsyncJob.idempotency_scope_key == scope_key,
            )
        )
        if replay is None:
            raise exc
        _assert_job_owner(replay, principal, cancel=False)
        if replay.request_fingerprint != fingerprint:
            raise ConflictError(
                "Idempotency key reused with different payload or operation"
            ) from exc
        return replay
    return job


def get_job_for_principal(
    session: Session, *, principal: RequestPrincipal, job_id: str
) -> DurableAsyncJob:
    job = session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == canonical_id(job_id)))
    if job is None:
        raise NotFoundError("Job not found")
    _assert_job_owner(job, principal, cancel=False)
    return job


def cancel_job(session: Session, *, principal: RequestPrincipal, job_id: str) -> DurableAsyncJob:
    job = get_job_for_principal(session, principal=principal, job_id=job_id)
    require_permission(principal.scopes, "jobs:cancel")
    if job.status in {s.value for s in TERMINAL_STATUSES}:
        return job
    _cas_job_status(
        session,
        job_id=job.id,
        expected_status=job.status,
        new_status=JobStatus.CANCELED.value,
        lease_holder=None,
        lease_fence=job.lease_fence + 1,
        clear_lease=True,
        canceled_at=datetime.now(UTC),
    )
    refreshed = session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == job.id))
    if refreshed is None:
        raise NotFoundError("Job not found")
    return refreshed


def claim_next_job(session: Session, *, worker_id: str) -> tuple[DurableAsyncJob, int] | None:
    now = datetime.now(UTC)
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
        terminal = job.attempts >= job.max_attempts
        session.execute(
            update(DurableAsyncJob)
            .where(
                DurableAsyncJob.id == job.id,
                DurableAsyncJob.status == job.status,
                DurableAsyncJob.lease_expires_at.is_not(None),
                DurableAsyncJob.lease_expires_at < now,
            )
            .values(
                status=JobStatus.FAILED.value if terminal else JobStatus.QUEUED.value,
                lease_holder=None,
                lease_expires_at=None,
                lease_fence=job.lease_fence + 1,
                completed_at=datetime.now(UTC) if terminal else None,
                error_code="MAX_ATTEMPTS" if terminal else None,
            )
        )
    session.flush()

    candidate = session.scalars(
        select(DurableAsyncJob)
        .where(
            DurableAsyncJob.status == JobStatus.QUEUED.value,
            DurableAsyncJob.synthetic_fixture_only.is_(True),
        )
        .order_by(DurableAsyncJob.created_at)
        .limit(1)
    ).first()
    if candidate is None:
        return None
    new_fence = candidate.lease_fence + 1
    new_attempts = candidate.attempts + 1
    claim_result = session.execute(
        update(DurableAsyncJob)
        .where(
            DurableAsyncJob.id == candidate.id,
            DurableAsyncJob.status == JobStatus.QUEUED.value,
            DurableAsyncJob.lease_holder.is_(None),
        )
        .values(
            lease_holder=worker_id,
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            lease_fence=new_fence,
            attempts=new_attempts,
            status=JobStatus.PLANNING.value,
        )
    )
    if getattr(claim_result, "rowcount", 0) != 1:
        return None
    session.flush()
    refreshed = session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == candidate.id))
    if refreshed is None:
        return None
    return refreshed, new_fence


def transition_job(
    session: Session,
    job: DurableAsyncJob,
    new_status: JobStatus,
    *,
    worker_id: str,
    lease_fence: int,
) -> None:
    current = JobStatus(job.status)
    if new_status not in LEGAL_TRANSITIONS[current]:
        raise ConflictError(f"Illegal transition {current.value} -> {new_status.value}")
    terminal = new_status in TERMINAL_STATUSES
    updated = _cas_job_status(
        session,
        job_id=job.id,
        expected_status=current.value,
        new_status=new_status.value,
        worker_id=worker_id,
        require_fence=lease_fence,
        completed_at=datetime.now(UTC) if terminal else None,
        clear_lease=terminal,
        lease_fence=lease_fence + 1 if terminal else lease_fence,
    )
    if updated != 1:
        raise ConflictError("Stale worker lease or job state changed")
    session.refresh(job)


def complete_synthetic_job(
    session: Session,
    job: DurableAsyncJob,
    *,
    worker_id: str,
    lease_fence: int,
) -> None:
    if not job.synthetic_fixture_only or job.capability_code != SYNTHETIC_JOB_CAPABILITY:
        raise CapabilityNotReadyError(
            capability=job.capability_code,
            reason="Non-synthetic jobs cannot complete without accepted readiness",
        )
    transition_job(session, job, JobStatus.COMPLETED, worker_id=worker_id, lease_fence=lease_fence)
    job.result_json = {
        "synthetic": True,
        "fixture_id": SYNTHETIC_INTERNAL_REQUEST["fixture_id"],
        "academic_readiness": False,
        "note": "Internal synthetic fixture only",
    }
    session.flush()


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