"""D17-25 durable worker — separate process entry."""

from __future__ import annotations

import logging
import time
import uuid

from app.db.session import session_factory
from app.platform.jobs.enums import JobStatus
from app.platform.jobs.service import claim_next_job, complete_synthetic_job, transition_job

logger = logging.getLogger("eduvijna.worker")


def run_worker_once(*, worker_id: str | None = None) -> bool:
    worker = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    session = session_factory()()
    try:
        job = claim_next_job(session, worker_id=worker)
        if job is None:
            session.commit()
            return False
        if job.synthetic_fixture_only:
            transition_job(session, job, JobStatus.GENERATING)
            transition_job(session, job, JobStatus.VALIDATING)
            complete_synthetic_job(session, job)
        else:
            job.status = JobStatus.FAILED.value
            job.error_code = "CAPABILITY_NOT_READY"
            job.result_json = {"blocked": True, "reason": "Non-synthetic worker path blocked"}
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.exception("Worker iteration failed")
        raise
    finally:
        session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        handled = run_worker_once()
        if not handled:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
