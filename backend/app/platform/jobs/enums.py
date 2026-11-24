from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING = "generating"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED})


LEGAL_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.PLANNING, JobStatus.CANCELED, JobStatus.FAILED}),
    JobStatus.PLANNING: frozenset({JobStatus.GENERATING, JobStatus.CANCELED, JobStatus.FAILED}),
    JobStatus.GENERATING: frozenset({JobStatus.VALIDATING, JobStatus.CANCELED, JobStatus.FAILED}),
    JobStatus.VALIDATING: frozenset(
        {JobStatus.REPAIRING, JobStatus.COMPLETED, JobStatus.CANCELED, JobStatus.FAILED}
    ),
    JobStatus.REPAIRING: frozenset(
        {JobStatus.VALIDATING, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELED: frozenset(),
}


SYNTHETIC_JOB_CAPABILITY = "platform.synthetic_echo"
