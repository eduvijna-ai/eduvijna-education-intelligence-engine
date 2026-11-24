from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.attempt_meta import harness_binding_from_attempt
from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.context import authorize_actor, load_bound_attempt
from app.learner_intelligence.contracts import (
    AttemptOutcome,
    FinalizeAttemptRequest,
    RecordResponseRequest,
    SnapshotItem,
)
from app.learner_intelligence.diagnostics import record_diagnostic_events
from app.learner_intelligence.enums import (
    MASTERY_POLICY_VERSION,
    AttemptState,
    EligibilityVerdict,
    IssueCode,
    ResponseKind,
    ScoringVerdict,
)
from app.learner_intelligence.gate import require_harness_or_blocked
from app.learner_intelligence.history import record_history_observation
from app.learner_intelligence.lifecycle import mark_responses_final, transition_attempt
from app.learner_intelligence.mastery import apply_mastery_update
from app.learner_intelligence.memory import append_memory_from_event
from app.learner_intelligence.scoring import aggregate_attempt_marks, score_item_response
from app.learner_intelligence.snapshot import (
    compute_assessment_fingerprint,
    verify_item_matches_persisted_row,
)
from app.models.learner_intelligence import (
    AssessmentAttempt,
    AttemptResponse,
    FinalizationIdempotencyRecord,
    IssuedItemSnapshot,
    ScoreEvidenceEvent,
)

HARNESS_BIND_KEY = "d15_harness_binding_secret"


class FinalizationError(Exception):
    def __init__(self, code: IssueCode, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)


def _snapshot_to_contract(row_json: dict[str, object], *, item_sequence: int) -> SnapshotItem:
    item = SnapshotItem.model_validate(dict(row_json))
    if item.item_sequence != item_sequence:
        raise FinalizationError(IssueCode.SNAPSHOT_MISMATCH)
    return item


def _verify_persisted_snapshots(session: Session, attempt_id: str) -> list[IssuedItemSnapshot]:
    rows = list(
        session.scalars(
            select(IssuedItemSnapshot)
            .where(IssuedItemSnapshot.attempt_id == attempt_id)
            .order_by(IssuedItemSnapshot.item_sequence)
        ).all()
    )
    for row in rows:
        item = _snapshot_to_contract(row.snapshot_json, item_sequence=row.item_sequence)
        if not verify_item_matches_persisted_row(
            item,
            row_fingerprint=row.content_fingerprint,
            row_marks_correct=row.marks_if_correct,
            row_marks_incorrect=row.marks_if_incorrect,
            row_marks_blank=row.marks_if_blank,
            policy_version=row.scoring_policy_version,
            row_question_id=row.question_id,
            row_item_sequence=row.item_sequence,
        ):
            raise FinalizationError(IssueCode.SNAPSHOT_MISMATCH)
    return rows


def _recompute_binding_fingerprint(session: Session, attempt_id: str) -> str:
    rows = _verify_persisted_snapshots(session, attempt_id)
    items = [
        _snapshot_to_contract(r.snapshot_json, item_sequence=r.item_sequence) for r in rows
    ]
    return compute_assessment_fingerprint(items)


def _verify_cached_idempotent_outcome(
    session: Session,
    *,
    attempt: AssessmentAttempt,
    cached: AttemptOutcome,
    binding: str,
    snapshot_count: int,
) -> None:
    events = list(
        session.scalars(
            select(ScoreEvidenceEvent)
            .where(ScoreEvidenceEvent.attempt_id == str(attempt.id))
            .order_by(ScoreEvidenceEvent.item_sequence)
        ).all()
    )
    if len(events) != snapshot_count:
        raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
    if cached.state != AttemptState.FINALIZED:
        raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
    if cached.total_marks is None or cached.max_marks is None:
        raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
    if attempt.total_marks != cached.total_marks or attempt.max_marks != cached.max_marks:
        raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
    if attempt.content_fingerprint != binding:
        raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
    for ev in events:
        if ev.snapshot_fingerprint is None:
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)


def finalize_attempt(session: Session, request: FinalizeAttemptRequest) -> AttemptOutcome:
    """D15-14/15: containment — no runtime persistence."""

    _ = request
    if not runtime_learner_db_io_allowed():
        raise FinalizationError(containment_issue())
    if require_harness_or_blocked(session) is not None:
        raise FinalizationError(IssueCode.NOT_ELIGIBLE)
    auth_err = authorize_actor(session, request.actor)
    if auth_err is not None:
        raise FinalizationError(auth_err)
    attempt, load_err = load_bound_attempt(session, request.actor, request.attempt_id)
    if load_err is not None or attempt is None:
        raise FinalizationError(load_err or IssueCode.OUT_OF_SCOPE)

    expected_binding = harness_binding_from_attempt(attempt)
    session_binding = session.info.get(HARNESS_BIND_KEY)
    if expected_binding and session_binding != expected_binding:
        raise FinalizationError(IssueCode.NOT_ELIGIBLE)

    binding = _recompute_binding_fingerprint(session, str(attempt.id))
    if request.content_binding_fingerprint != binding:
        raise FinalizationError(IssueCode.SNAPSHOT_MISMATCH)
    if attempt.content_fingerprint != binding:
        raise FinalizationError(IssueCode.SNAPSHOT_MISMATCH)

    snapshots = _verify_persisted_snapshots(session, str(attempt.id))
    snapshot_count = len(snapshots)

    idem = session.scalar(
        select(FinalizationIdempotencyRecord).where(
            FinalizationIdempotencyRecord.organization_id == attempt.organization_id,
            FinalizationIdempotencyRecord.institution_id == attempt.institution_id,
            FinalizationIdempotencyRecord.learner_id == attempt.learner_id,
            FinalizationIdempotencyRecord.idempotency_key == request.idempotency_key,
        )
    )
    if idem is not None:
        if idem.content_binding_fingerprint != binding:
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
        if idem.attempt_id != str(attempt.id):
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
        if idem.institution_id != attempt.institution_id:
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
        cached = AttemptOutcome.model_validate(idem.outcome_json)
        _verify_cached_idempotent_outcome(
            session,
            attempt=attempt,
            cached=cached,
            binding=binding,
            snapshot_count=snapshot_count,
        )
        return cached.model_copy(update={"committed": True})

    state = AttemptState(attempt.state)
    if state == AttemptState.FINALIZED:
        return AttemptOutcome(
            attempt_id=str(attempt.id),
            state=AttemptState.FINALIZED,
            eligibility_verdict=EligibilityVerdict.ELIGIBLE,
            committed=True,
            total_marks=attempt.total_marks,
            max_marks=attempt.max_marks,
        )
    if state != AttemptState.IN_PROGRESS:
        raise FinalizationError(IssueCode.INVALID_TRANSITION)

    responses = list(
        session.scalars(
            select(AttemptResponse).where(AttemptResponse.attempt_id == str(attempt.id))
        ).all()
    )
    by_seq = {r.item_sequence: r for r in responses}
    outcomes: list[dict[str, object]] = []
    item_scores = []
    pending_review = False

    transition_attempt(session, attempt, AttemptState.SUBMITTED)
    for snap_row in snapshots:
        contract = _snapshot_to_contract(
            snap_row.snapshot_json,
            item_sequence=snap_row.item_sequence,
        )
        resp = by_seq.get(snap_row.item_sequence)
        if resp is None:
            req = RecordResponseRequest(
                actor=request.actor,
                attempt_id=str(attempt.id),
                item_sequence=snap_row.item_sequence,
                response_kind=ResponseKind.UNANSWERED,
            )
        else:
            req = RecordResponseRequest(
                actor=request.actor,
                attempt_id=str(attempt.id),
                item_sequence=resp.item_sequence,
                response_kind=ResponseKind(resp.response_kind),
                selected_option_keys=list(resp.selected_option_keys_json or []),
                numeric_value=resp.numeric_value,
                descriptive_text=resp.descriptive_text,
            )
        scored = score_item_response(contract, req)
        item_scores.append(scored)
        if scored.verdict == ScoringVerdict.REVIEW_REQUIRED:
            pending_review = True
        if scored.verdict != ScoringVerdict.REVIEW_REQUIRED:
            event = ScoreEvidenceEvent(
                attempt_id=str(attempt.id),
                organization_id=attempt.organization_id,
                learner_id=attempt.learner_id,
                item_sequence=snap_row.item_sequence,
                verdict=scored.verdict.value,
                marks_awarded=scored.marks_awarded,
                max_marks=scored.max_marks,
                snapshot_fingerprint=snap_row.content_fingerprint,
                concept_codes_json=list(contract.concept_codes),
                policy_version=MASTERY_POLICY_VERSION,
                metadata_json={"assessment_key": attempt.assessment_key},
            )
            session.add(event)
            session.flush()
            for code in contract.concept_codes:
                apply_mastery_update(
                    session,
                    organization_id=attempt.organization_id,
                    institution_id=attempt.institution_id,
                    learner_id=attempt.learner_id,
                    concept_code=code,
                    event=event,
                )
            record_history_observation(
                session,
                organization_id=attempt.organization_id,
                learner_id=attempt.learner_id,
                attempt_id=str(attempt.id),
                question_id=contract.question_id,
                item_sequence=snap_row.item_sequence,
                source_version=contract.source_version,
                score=scored,
            )
            if resp is not None:
                record_diagnostic_events(
                    session,
                    organization_id=attempt.organization_id,
                    institution_id=attempt.institution_id,
                    learner_id=attempt.learner_id,
                    attempt_id=str(attempt.id),
                    item=contract,
                    selected_option_keys=list(resp.selected_option_keys_json or []),
                    score=scored,
                    response_id=str(resp.id),
                )
            append_memory_from_event(
                session,
                organization_id=attempt.organization_id,
                learner_id=attempt.learner_id,
                memory_key=f"item:{attempt.id}:{snap_row.item_sequence}",
                event=event,
                payload={"verdict": scored.verdict.value},
            )
        outcomes.append(
            {
                "item_sequence": snap_row.item_sequence,
                "verdict": scored.verdict.value,
                "marks_awarded": str(scored.marks_awarded),
            }
        )
    if pending_review:
        raise FinalizationError(IssueCode.REVIEW_PENDING)
    total, max_marks = aggregate_attempt_marks(item_scores)
    attempt.total_marks = total
    attempt.max_marks = max_marks
    mark_responses_final(session, str(attempt.id))
    transition_attempt(session, attempt, AttemptState.FINALIZED)
    outcome = AttemptOutcome(
        attempt_id=str(attempt.id),
        state=AttemptState.FINALIZED,
        eligibility_verdict=EligibilityVerdict.ELIGIBLE,
        committed=False,
        total_marks=total,
        max_marks=max_marks,
        item_outcomes=outcomes,
    )
    session.add(
        FinalizationIdempotencyRecord(
            organization_id=attempt.organization_id,
            institution_id=attempt.institution_id,
            learner_id=attempt.learner_id,
            attempt_id=str(attempt.id),
            idempotency_key=request.idempotency_key,
            content_binding_fingerprint=binding,
            outcome_json=json.loads(outcome.model_dump_json()),
        )
    )
    session.flush()
    if session.info.get("d15_harness_owned"):
        return outcome.model_copy(update={"committed": True})
    return outcome.model_copy(update={"committed": True})