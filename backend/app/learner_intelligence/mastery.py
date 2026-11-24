from __future__ import annotations

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


def _confidence(attempts: int) -> MasteryConfidence:
    if attempts < 5:
        return MasteryConfidence.LOW
    if attempts < 15:
        return MasteryConfidence.MEDIUM
    return MasteryConfidence.HIGH


def _level(correct: int, incorrect: int) -> MasteryLevel:
    attempts = correct + incorrect
    if attempts < 2:
        return MasteryLevel.UNKNOWN
    accuracy = correct / attempts if attempts else 0.0
    if accuracy >= 0.75 and correct >= 3:
        return MasteryLevel.SECURE
    if accuracy >= 0.4:
        return MasteryLevel.DEVELOPING
    return MasteryLevel.EMERGING


def compute_mastery_from_events(
    events: list[ScoreEvidenceEvent],
    *,
    concept_code: str,
) -> MasterySnapshot:
    correct = 0
    incorrect = 0
    for ev in events:
        if concept_code not in (ev.concept_codes_json or []):
            continue
        if ev.verdict == ScoringVerdict.CORRECT.value:
            correct += 1
        elif ev.verdict in (ScoringVerdict.INCORRECT.value, ScoringVerdict.PARTIAL.value):
            incorrect += 1
    attempts = correct + incorrect
    return MasterySnapshot(
        concept_code=concept_code,
        level=_level(correct, incorrect),
        confidence=_confidence(attempts),
        support_correct=correct,
        support_incorrect=incorrect,
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
    snap = compute_mastery_from_events(events, concept_code=concept_code)
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