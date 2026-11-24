from __future__ import annotations

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import MasterySnapshot
from app.learner_intelligence.enums import (
    MASTERY_POLICY_VERSION,
    MasteryConfidence,
    MasteryLevel,
    ScoringVerdict,
)
from app.models.learner_intelligence import ConceptMasteryRecord, ScoreEvidenceEvent

_RECENCY_WINDOW = 10
_OLDER_WEIGHT = 0.25


def _confidence(weighted_attempts: float) -> MasteryConfidence:
    if weighted_attempts < 5:
        return MasteryConfidence.LOW
    if weighted_attempts < 15:
        return MasteryConfidence.MEDIUM
    return MasteryConfidence.HIGH


def _level(
    weighted_correct: float,
    weighted_incorrect: float,
    *,
    last_three_all_wrong: bool,
    had_prior_strength: bool,
) -> MasteryLevel:
    attempts = weighted_correct + weighted_incorrect
    if attempts < 2:
        return MasteryLevel.UNKNOWN
    if last_three_all_wrong and had_prior_strength:
        return MasteryLevel.REGRESSION_FLAGGED
    accuracy = weighted_correct / attempts if attempts else 0.0
    if accuracy >= 0.75 and weighted_correct >= 3:
        return MasteryLevel.SECURE
    if accuracy >= 0.4:
        return MasteryLevel.DEVELOPING
    return MasteryLevel.EMERGING


def compute_mastery_from_events(
    events: list[ScoreEvidenceEvent],
    *,
    concept_code: str,
    organization_id: str,
    learner_id: str,
) -> MasterySnapshot:
    scoped = [
        ev
        for ev in events
        if ev.organization_id == organization_id
        and ev.learner_id == learner_id
        and concept_code in (ev.concept_codes_json or [])
        and ev.verdict
        in (
            ScoringVerdict.CORRECT.value,
            ScoringVerdict.INCORRECT.value,
            ScoringVerdict.PARTIAL.value,
        )
    ]
    def _event_order_key(ev: ScoreEvidenceEvent) -> tuple[float, int]:
        ts = ev.created_at
        if ts is None:
            return (0.0, ev.item_sequence)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (ts.timestamp(), ev.item_sequence)

    scoped.sort(key=_event_order_key, reverse=True)
    recent = scoped[:_RECENCY_WINDOW]
    older = scoped[_RECENCY_WINDOW:]

    def weight(count: int, *, recent_bucket: bool) -> float:
        return float(count) * (1.0 if recent_bucket else _OLDER_WEIGHT)

    correct = 0.0
    incorrect = 0.0
    for ev in recent:
        if ev.verdict == ScoringVerdict.CORRECT.value:
            correct += weight(1, recent_bucket=True)
        elif ev.verdict in (ScoringVerdict.INCORRECT.value, ScoringVerdict.PARTIAL.value):
            incorrect += weight(1, recent_bucket=True)
    for ev in older:
        if ev.verdict == ScoringVerdict.CORRECT.value:
            correct += weight(1, recent_bucket=False)
        elif ev.verdict in (ScoringVerdict.INCORRECT.value, ScoringVerdict.PARTIAL.value):
            incorrect += weight(1, recent_bucket=False)

    last_three = recent[:3]
    last_three_all_wrong = len(last_three) == 3 and all(
        e.verdict in (ScoringVerdict.INCORRECT.value, ScoringVerdict.PARTIAL.value)
        for e in last_three
    )
    had_prior_strength = len(older) >= 3 and (correct + incorrect) >= 5

    attempts = correct + incorrect
    return MasterySnapshot(
        concept_code=concept_code,
        level=_level(
            correct,
            incorrect,
            last_three_all_wrong=last_three_all_wrong,
            had_prior_strength=had_prior_strength,
        ),
        confidence=_confidence(attempts),
        support_correct=max(0, int(round(correct))),
        support_incorrect=max(0, int(round(incorrect))),
        policy_version=MASTERY_POLICY_VERSION,
    )


def apply_mastery_update(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
    concept_code: str,
    event: ScoreEvidenceEvent,
) -> ConceptMasteryRecord:
    existing = session.scalar(
        select(ConceptMasteryRecord).where(
            ConceptMasteryRecord.organization_id == organization_id,
            ConceptMasteryRecord.institution_id == institution_id,
            ConceptMasteryRecord.learner_id == learner_id,
            ConceptMasteryRecord.concept_code == concept_code,
            ConceptMasteryRecord.policy_version == MASTERY_POLICY_VERSION,
        )
    )
    query = select(ScoreEvidenceEvent).where(
        ScoreEvidenceEvent.learner_id == learner_id,
        ScoreEvidenceEvent.organization_id == organization_id,
    )
    events = list(session.scalars(query))
    snap = compute_mastery_from_events(
        events,
        concept_code=concept_code,
        organization_id=organization_id,
        learner_id=learner_id,
    )
    if existing is None:
        existing = ConceptMasteryRecord(
            organization_id=organization_id,
            institution_id=institution_id,
            learner_id=learner_id,
            concept_code=concept_code,
            policy_version=MASTERY_POLICY_VERSION,
            mastery_level=snap.level.value,
            confidence=snap.confidence.value,
            support_correct=snap.support_correct,
            support_incorrect=snap.support_incorrect,
            last_evidence_event_id=str(event.id),
        )
        session.add(existing)
    else:
        existing.mastery_level = snap.level.value
        existing.confidence = snap.confidence.value
        existing.support_correct = snap.support_correct
        existing.support_incorrect = snap.support_incorrect
        existing.last_evidence_event_id = str(event.id)
    return existing