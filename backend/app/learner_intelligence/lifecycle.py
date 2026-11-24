from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue
from app.learner_intelligence.contracts import RecordResponseRequest, SnapshotItem
from app.learner_intelligence.enums import AttemptState, IssueCode
from app.models.learner_intelligence import AssessmentAttempt, AttemptResponse, IssuedItemSnapshot


class LifecycleBlockedError(Exception):
    def __init__(self, code: IssueCode) -> None:
        self.code = code
        super().__init__(code.value)


def _blocked() -> None:
    raise LifecycleBlockedError(containment_issue())


def transition_attempt(
    session: Session,
    attempt: AssessmentAttempt,
    new_state: AttemptState,
) -> None:
    _ = (session, attempt, new_state)
    _blocked()


def load_snapshot_item(session: Session, attempt_id: str, item_sequence: int) -> IssuedItemSnapshot:
    _ = (session, attempt_id, item_sequence)
    _blocked()
    raise AssertionError("unreachable")


def validate_and_store_response(
    session: Session,
    attempt: AssessmentAttempt,
    request: RecordResponseRequest,
    *,
    item_model_json: dict[str, object],
) -> tuple[AttemptResponse | None, list[IssueCode]]:
    _ = (session, attempt, request, item_model_json)
    return None, [containment_issue()]


def preview_score_for_draft(
    session: Session,
    attempt_id: str,
    request: RecordResponseRequest,
    item_contract: SnapshotItem,
) -> None:
    _ = (session, attempt_id, request, item_contract)
    _blocked()


def mark_responses_final(session: Session, attempt_id: str) -> None:
    _ = (session, attempt_id)
    _blocked()


def abandon_attempt(session: Session, attempt: AssessmentAttempt) -> None:
    _ = (session, attempt)
    _blocked()