"""D17-25 durable worker — separate process entry."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import session_factory
from app.models.platform_jobs import DurableAsyncJob
from app.platform.jobs.enums import JobStatus
from app.platform.jobs.service import claim_next_job, complete_synthetic_job, transition_job

logger = logging.getLogger("eduvijna.worker")


def run_worker_once(*, worker_id: str | None = None) -> bool:
    worker = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    session = session_factory()()
    try:
        claimed = claim_next_job(session, worker_id=worker)
        if claimed is None:
            session.commit()
            return False
        job, fence = claimed
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Worker claim failed")
        return False
    finally:
        session.close()

    work_session = session_factory()()
    try:
        live = work_session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == job.id))
        if live is None:
            return False
        if not live.synthetic_fixture_only:
            live.status = JobStatus.FAILED.value
            live.error_code = "CAPABILITY_NOT_READY"
            live.result_json = {"blocked": True, "reason": "Non-synthetic worker path blocked"}
            work_session.commit()
            return True
        transition_job(
            work_session, live, JobStatus.GENERATING, worker_id=worker, lease_fence=fence
        )
        transition_job(
            work_session, live, JobStatus.VALIDATING, worker_id=worker, lease_fence=fence
        )
        complete_synthetic_job(work_session, live, worker_id=worker, lease_fence=fence)
        work_session.commit()
        return True
    except Exception:
        work_session.rollback()
        logger.exception("Worker iteration failed")
        fail_session = session_factory()()
        try:
            live = fail_session.scalar(select(DurableAsyncJob).where(DurableAsyncJob.id == job.id))
            if live and live.lease_holder == worker and live.lease_fence == fence:
                if live.attempts >= live.max_attempts:
                    live.status = JobStatus.FAILED.value
                    live.error_code = "WORKER_ERROR"
                    live.completed_at = datetime.now(UTC)
                else:
                    live.status = JobStatus.QUEUED.value
                    live.lease_holder = None
                    live.lease_expires_at = None
                fail_session.commit()
        finally:
            fail_session.close()
        return False
    finally:
        work_session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        handled = run_worker_once()
        if not handled:
            time.sleep(0.5)


if __name__ == "__main__":
    main()