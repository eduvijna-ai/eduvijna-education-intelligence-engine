from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.platform_jobs import DurableAsyncJob
from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.jobs.service import enqueue_job
from app.platform.jobs.synthetic import SYNTHETIC_INTERNAL_REQUEST, SYNTHETIC_JOB_CAPABILITY


def enqueue_internal_synthetic_fixture(
    session: Session,
    *,
    principal: RequestPrincipal,
    idempotency_key: str,
) -> DurableAsyncJob:
    """Test/worker harness only — not exposed via public REST enqueue."""
    require_permission(principal.scopes, "jobs:submit")
    return enqueue_job(
        session,
        principal=principal,
        capability_code=SYNTHETIC_JOB_CAPABILITY,
        idempotency_key=idempotency_key,
        request_payload=dict(SYNTHETIC_INTERNAL_REQUEST),
        synthetic_fixture_only=True,
    )