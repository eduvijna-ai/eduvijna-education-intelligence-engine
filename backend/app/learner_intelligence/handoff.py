from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.context import authorize_actor
from app.learner_intelligence.contracts import RemediationHandoff, TrustedActorContext
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION, MasteryLevel
from app.models.learner_intelligence import (
    ConceptMasteryRecord,
    DiagnosticProfileEvent,
    ScoreEvidenceEvent,
)


def build_day16_handoff(
    session: Session,
    actor: TrustedActorContext,
) -> RemediationHandoff:
    """D15-31: NOT_READY unless scoped evidence exists; UNKNOWN is not a proven weakness."""

    err = authorize_actor(session, actor)
    if err is not None:
        return RemediationHandoff(
            readiness="NOT_READY",
            learner_id=actor.learner_id,
            organization_id=actor.organization_id,
            institution_id=actor.institution_id,
            policy_version=MASTERY_POLICY_VERSION,
        )

    mastery_rows = session.scalars(
        select(ConceptMasteryRecord).where(
            ConceptMasteryRecord.organization_id == actor.organization_id,
            ConceptMasteryRecord.institution_id == actor.institution_id,
            ConceptMasteryRecord.learner_id == actor.learner_id,
        )
    ).all()
    gaps = [
        r.concept_code
        for r in mastery_rows
        if r.mastery_level
        in (
            MasteryLevel.EMERGING.value,
            MasteryLevel.REGRESSION_FLAGGED.value,
            MasteryLevel.DEVELOPING.value,
        )
    ]
    diag_rows = session.scalars(
        select(DiagnosticProfileEvent).where(
            DiagnosticProfileEvent.organization_id == actor.organization_id,
            DiagnosticProfileEvent.learner_id == actor.learner_id,
        )
    ).all()
    misconceptions = sorted({d.misconception_code for d in diag_rows})
    attempt_ids = sorted({d.attempt_id for d in diag_rows})
    evidence_ids = [
        str(e.id)
        for e in session.scalars(
            select(ScoreEvidenceEvent).where(
                ScoreEvidenceEvent.organization_id == actor.organization_id,
                ScoreEvidenceEvent.learner_id == actor.learner_id,
            )
        ).all()
    ]
    readiness = "READY" if gaps or misconceptions else "NOT_READY"
    return RemediationHandoff(
        readiness=readiness,
        learner_id=actor.learner_id,
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        concept_gaps=gaps,
        misconception_codes=misconceptions,
        prerequisite_hypothesis_ids=[],
        source_attempt_ids=attempt_ids,
        evidence_event_ids=evidence_ids,
        policy_version=MASTERY_POLICY_VERSION,
    )