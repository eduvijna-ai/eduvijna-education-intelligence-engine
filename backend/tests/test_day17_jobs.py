from __future__ import annotations

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine, get_settings, session_factory
from app.platform.auth.principal import RequestPrincipal
from app.platform.jobs.enums import JobStatus
from app.platform.jobs.internal_harness import enqueue_internal_synthetic_fixture
from app.platform.jobs.service import cancel_job
from app.platform.jobs.worker import run_worker_once
from tests.day17_fixtures import seed_tenant_with_teacher


def _principal(org_id: str, inst_id: str, principal_id: str) -> RequestPrincipal:
    return RequestPrincipal(
        principal_id=principal_id,
        organization_id=org_id,
        institution_id=inst_id,
        role="institution_admin",
        scopes=("jobs:submit", "jobs:read", "jobs:cancel"),
        actor_kind="teacher",
        actor_ref="teacher-ref",
        auth_method="bearer",
    )


def test_job_enqueue_idempotency_and_synthetic_worker(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'jobs.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    create_database_engine.cache_clear()
    engine = create_database_engine(db_url)
    Base.metadata.create_all(engine)

    session = session_factory()()
    try:
        org, inst, _, _ = seed_tenant_with_teacher(session)
        from sqlalchemy import select

        from app.models.platform_auth import ApplicationPrincipal

        principal_row = session.scalar(select(ApplicationPrincipal).limit(1))
        assert principal_row is not None
        session.commit()
        principal = _principal(org.id, inst.id, principal_row.id)
        job_a = enqueue_internal_synthetic_fixture(
            session, principal=principal, idempotency_key="idem-1"
        )
        job_b = enqueue_internal_synthetic_fixture(
            session, principal=principal, idempotency_key="idem-1"
        )
        assert job_a.id == job_b.id
        session.commit()

        session.commit()

        handled = run_worker_once(worker_id="worker-a")
        assert handled is True

        refreshed = session_factory()()
        try:
            from app.platform.jobs.service import get_job_for_principal

            job = get_job_for_principal(refreshed, principal=principal, job_id=job_a.id)
            assert job.status == JobStatus.COMPLETED.value
            assert job.result_json.get("synthetic") is True
            assert job.result_json.get("academic_readiness") is False
            canceled = cancel_job(refreshed, principal=principal, job_id=job_a.id)
            assert canceled.status == JobStatus.COMPLETED.value
            refreshed.commit()
        finally:
            refreshed.close()
    finally:
        session.close()
