from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.learner_intelligence.history import record_history_observation
from app.learner_intelligence.lifecycle import (
    load_snapshot_item,
    mark_responses_final,
    transition_attempt,
)
from app.learner_intelligence.mastery import apply_mastery_update
from app.learner_intelligence.memory import append_memory_from_event
from app.learner_intelligence.scoring import aggregate_attempt_marks, score_item_response
from app.learner_intelligence.snapshot import compute_assessment_fingerprint
from app.models.learner_intelligence import (
    AssessmentAttempt,
    AttemptResponse,
    FinalizationIdempotencyRecord,
    ScoreEvidenceEvent,
)


class FinalizationError(Exception):
    def __init__(self, code: IssueCode, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)


def _snapshot_to_contract(row_json: dict[str, object], *, item_sequence: int) -> SnapshotItem:
    row_json = dict(row_json)
    row_json["item_sequence"] = item_sequence
    return SnapshotItem.model_validate(row_json)


def finalize_attempt(
    session: Session,
    attempt: AssessmentAttempt,
    request: FinalizeAttemptRequest,
) -> AttemptOutcome:
    """D15-14/15: single owned transaction; idempotent replay."""

    if request.actor.learner_id != attempt.learner_id:
        raise FinalizationError(IssueCode.TENANT_MISMATCH)
    if request.content_binding_fingerprint != attempt.content_fingerprint:
        raise FinalizationError(IssueCode.SNAPSHOT_MISMATCH)

    idem = session.scalar(
        select(FinalizationIdempotencyRecord).where(
            FinalizationIdempotencyRecord.organization_id == attempt.organization_id,
            FinalizationIdempotencyRecord.learner_id == attempt.learner_id,
            FinalizationIdempotencyRecord.idempotency_key == request.idempotency_key,
        )
    )
    if idem is not None:
        if idem.content_binding_fingerprint != request.content_binding_fingerprint:
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
        if idem.attempt_id != str(attempt.id):
            raise FinalizationError(IssueCode.IDEMPOTENCY_CONFLICT)
        cached = AttemptOutcome.model_validate(idem.outcome_json)
        return cached

    if AttemptState(attempt.state) not in (AttemptState.IN_PROGRESS, AttemptState.CREATED):
        if AttemptState(attempt.state) == AttemptState.FINALIZED:
            return AttemptOutcome(
                attempt_id=str(attempt.id),
                state=AttemptState.FINALIZED,
                eligibility_verdict=EligibilityVerdict.ELIGIBLE,
                committed=True,
                total_marks=attempt.total_marks,
                max_marks=attempt.max_marks,
            )
        raise FinalizationError(IssueCode.INVALID_TRANSITION)

    responses = list(
        session.scalars(
            select(AttemptResponse).where(AttemptResponse.attempt_id == str(attempt.id))
        ).all()
    )
    outcomes: list[dict[str, object]] = []
    item_scores = []
    try:
        transition_attempt(session, attempt, AttemptState.SUBMITTED)
        for resp in responses:
            snap_row = load_snapshot_item(session, str(attempt.id), resp.item_sequence)
            contract = _snapshot_to_contract(
                snap_row.snapshot_json,
                item_sequence=resp.item_sequence,
            )
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
            if scored.verdict != ScoringVerdict.REVIEW_REQUIRED:
                event = ScoreEvidenceEvent(
                    attempt_id=str(attempt.id),
                    organization_id=attempt.organization_id,
                    learner_id=attempt.learner_id,
                    item_sequence=resp.item_sequence,
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
                    item_sequence=resp.item_sequence,
                    source_version=contract.source_version,
                    score=scored,
                )
                record_diagnostic_events(
                    session,
                    organization_id=attempt.organization_id,
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
                    memory_key=f"item:{attempt.id}:{resp.item_sequence}",
                    event=event,
                    payload={"verdict": scored.verdict.value},
                )
            outcomes.append(
                {
                    "item_sequence": resp.item_sequence,
                    "verdict": scored.verdict.value,
                    "marks_awarded": str(scored.marks_awarded),
                }
            )
        total, max_marks = aggregate_attempt_marks(item_scores)
        attempt.total_marks = total
        attempt.max_marks = max_marks
        mark_responses_final(session, str(attempt.id))
        transition_attempt(session, attempt, AttemptState.FINALIZED)
        outcome = AttemptOutcome(
            attempt_id=str(attempt.id),
            state=AttemptState.FINALIZED,
            eligibility_verdict=EligibilityVerdict.ELIGIBLE,
            committed=True,
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
                content_binding_fingerprint=request.content_binding_fingerprint,
                outcome_json=json.loads(outcome.model_dump_json()),
            )
        )
        session.commit()
        return outcome
    except Exception as exc:
        session.rollback()
        if isinstance(exc, FinalizationError):
            raise
        raise FinalizationError(IssueCode.FINALIZATION_ROLLBACK) from exc


def verify_attempt_fingerprint(items: list[SnapshotItem], stored: str) -> bool:
    return compute_assessment_fingerprint(items) == stored