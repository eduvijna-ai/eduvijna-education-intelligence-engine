from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import AttemptOutcome
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, IssueCode


def require_harness_or_blocked(
    session: Session,
    *,
    attempt_binding: str | None = None,
) -> IssueCode | None:
    _ = (session, attempt_binding)
    if runtime_learner_db_io_allowed():
        return None
    return containment_issue()


def blocked_outcome(
    attempt_id: str = "",
    code: IssueCode | None = None,
) -> AttemptOutcome:
    issue = code or containment_issue()
    return AttemptOutcome(
        attempt_id=attempt_id,
        state=AttemptState.CREATED,
        eligibility_verdict=EligibilityVerdict.BLOCKED_UNVERIFIED,
        issue_codes=[issue],
        committed=False,
    )