from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import RecordResponseRequest, SnapshotItem
from app.learner_intelligence.enums import AttemptState, IssueCode
from app.learner_intelligence.scoring import score_item_response
from app.learner_intelligence.snapshot import compute_item_fingerprint
from app.models.learner_intelligence import AssessmentAttempt, AttemptResponse, IssuedItemSnapshot

_LEGAL: dict[AttemptState, frozenset[AttemptState]] = {
    AttemptState.CREATED: frozenset({AttemptState.IN_PROGRESS, AttemptState.ABANDONED}),
    AttemptState.IN_PROGRESS: frozenset(
        {AttemptState.IN_PROGRESS, AttemptState.SUBMITTED, AttemptState.ABANDONED}
    ),
    AttemptState.SUBMITTED: frozenset({AttemptState.FINALIZED}),
    AttemptState.FINALIZED: frozenset(),
    AttemptState.ABANDONED: frozenset(),
}


def transition_attempt(
    session: Session,
    attempt: AssessmentAttempt,
    new_state: AttemptState,
) -> None:
    current = AttemptState(attempt.state)
    if new_state not in _LEGAL.get(current, frozenset()):
        raise ValueError(IssueCode.INVALID_TRANSITION.value)
    attempt.state = new_state.value
    now = datetime.now(UTC)
    if new_state == AttemptState.IN_PROGRESS and attempt.started_at is None:
        attempt.started_at = now
    if new_state == AttemptState.SUBMITTED:
        attempt.submitted_at = now
    if new_state == AttemptState.FINALIZED:
        attempt.finalized_at = now


def load_snapshot_item(session: Session, attempt_id: str, item_sequence: int) -> IssuedItemSnapshot:
    row = session.scalar(
        select(IssuedItemSnapshot).where(
            IssuedItemSnapshot.attempt_id == attempt_id,
            IssuedItemSnapshot.item_sequence == item_sequence,
        )
    )
    if row is None:
        raise ValueError(IssueCode.UNKNOWN_QUESTION.value)
    return row


def validate_and_store_response(
    session: Session,
    attempt: AssessmentAttempt,
    request: RecordResponseRequest,
    *,
    item_model_json: dict[str, object],
) -> tuple[AttemptResponse | None, list[IssueCode]]:
    """D15-08/09: draft responses; no scoring side effects here."""

    if request.actor.organization_id != attempt.organization_id:
        return _reject(IssueCode.CROSS_TENANT)
    if request.actor.learner_id != attempt.learner_id:
        return _reject(IssueCode.TENANT_MISMATCH)
    if request.actor.institution_id != attempt.institution_id:
        return _reject(IssueCode.TENANT_MISMATCH)
    if request.attempt_id != str(attempt.id):
        return _reject(IssueCode.OUT_OF_SCOPE)
    state = AttemptState(attempt.state)
    if state not in (AttemptState.IN_PROGRESS, AttemptState.CREATED):
        return _reject(IssueCode.INVALID_TRANSITION)

    raw_options = item_model_json.get("options")
    options = raw_options if isinstance(raw_options, list) else []
    option_keys = {
        str(o.get("option_key"))
        for o in options
        if isinstance(o, dict) and o.get("option_key") is not None
    }
    for key in request.selected_option_keys:
        if key not in option_keys:
            return _reject(IssueCode.UNKNOWN_OPTION)

    existing = session.scalar(
        select(AttemptResponse).where(
            AttemptResponse.attempt_id == str(attempt.id),
            AttemptResponse.item_sequence == request.item_sequence,
        )
    )
    if existing is not None and existing.is_final:
        return _reject(IssueCode.DUPLICATE_RESPONSE)

    if existing is None:
        existing = AttemptResponse(
            attempt_id=str(attempt.id),
            item_sequence=request.item_sequence,
            response_kind=request.response_kind.value,
            selected_option_keys_json=list(request.selected_option_keys),
            numeric_value=request.numeric_value,
            descriptive_text=request.descriptive_text,
            is_final=False,
        )
        session.add(existing)
    else:
        existing.response_kind = request.response_kind.value
        existing.selected_option_keys_json = list(request.selected_option_keys)
        existing.numeric_value = request.numeric_value
        existing.descriptive_text = request.descriptive_text

    if state == AttemptState.CREATED:
        transition_attempt(session, attempt, AttemptState.IN_PROGRESS)
    return existing, []


def _reject(code: IssueCode) -> tuple[None, list[IssueCode]]:
    return None, [code]


def preview_score_for_draft(
    session: Session,
    attempt_id: str,
    request: RecordResponseRequest,
    item_contract: SnapshotItem,
) -> None:
    """Guards only — final scoring happens at finalize."""

    row = load_snapshot_item(session, attempt_id, request.item_sequence)
    if row.content_fingerprint != compute_item_fingerprint(item_contract):
        raise ValueError(IssueCode.SNAPSHOT_MISMATCH.value)
    _ = score_item_response(item_contract, request)


def mark_responses_final(session: Session, attempt_id: str) -> None:
    rows = session.scalars(
        select(AttemptResponse).where(AttemptResponse.attempt_id == attempt_id)
    ).all()
    for row in rows:
        row.is_final = True


def abandon_attempt(session: Session, attempt: AssessmentAttempt) -> None:
    transition_attempt(session, attempt, AttemptState.ABANDONED)