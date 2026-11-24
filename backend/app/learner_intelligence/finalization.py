from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue
from app.learner_intelligence.contracts import (
    AttemptOutcome,
    FinalizeAttemptRequest,
)
from app.learner_intelligence.enums import IssueCode
from app.models.learner_intelligence import AssessmentAttempt


class FinalizationError(Exception):
    def __init__(self, code: IssueCode, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)


def _verify_persisted_snapshots(session: Session, attempt_id: str) -> list[object]:
    _ = (session, attempt_id)
    raise FinalizationError(containment_issue())


def _recompute_binding_fingerprint(session: Session, attempt_id: str) -> str:
    _ = (session, attempt_id)
    raise FinalizationError(containment_issue())


def _verify_cached_idempotent_outcome(
    session: Session,
    *,
    attempt: AssessmentAttempt,
    cached: AttemptOutcome,
    binding: str,
    snapshot_count: int,
) -> None:
    _ = (session, attempt, cached, binding, snapshot_count)
    raise FinalizationError(containment_issue())


def finalize_attempt(session: Session, request: FinalizeAttemptRequest) -> AttemptOutcome:
    _ = (session, request)
    raise FinalizationError(containment_issue())