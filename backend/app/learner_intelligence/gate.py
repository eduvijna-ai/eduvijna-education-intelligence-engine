from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import AttemptOutcome
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, IssueCode
from app.learner_intelligence.harness_runtime import harness_session_authorized


def require_harness_or_blocked(
    session: Session,
    *,
    attempt_binding: str | None = None,
) -> IssueCode | None:
    if not harness_session_authorized(session, expected_binding=attempt_binding):
        return IssueCode.NOT_ELIGIBLE
    return None


def blocked_outcome(
    attempt_id: str = "",
    code: IssueCode = IssueCode.NOT_ELIGIBLE,
) -> AttemptOutcome:
    return AttemptOutcome(
        attempt_id=attempt_id,
        state=AttemptState.CREATED,
        eligibility_verdict=EligibilityVerdict.BLOCKED_UNVERIFIED,
        issue_codes=[code],
        committed=False,
    )