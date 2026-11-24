from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import RemediationHandoff
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION, MasteryLevel
from app.models.learner_intelligence import ConceptMasteryRecord, DiagnosticProfileEvent


def build_day16_handoff(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
) -> RemediationHandoff:
    """D15-31: typed remediation needs only; no adaptive scheduling."""

    mastery_rows = session.scalars(
        select(ConceptMasteryRecord).where(
            ConceptMasteryRecord.organization_id == organization_id,
            ConceptMasteryRecord.learner_id == learner_id,
        )
    ).all()
    gaps = [
        r.concept_code
        for r in mastery_rows
        if r.mastery_level
        in (
            MasteryLevel.UNKNOWN.value,
            MasteryLevel.EMERGING.value,
            MasteryLevel.REGRESSION_FLAGGED.value,
        )
    ]
    diag_rows = session.scalars(
        select(DiagnosticProfileEvent).where(
            DiagnosticProfileEvent.organization_id == organization_id,
            DiagnosticProfileEvent.learner_id == learner_id,
        )
    ).all()
    misconceptions = sorted({d.misconception_code for d in diag_rows})
    attempt_ids = sorted({d.attempt_id for d in diag_rows})
    return RemediationHandoff(
        learner_id=learner_id,
        organization_id=organization_id,
        institution_id=institution_id,
        concept_gaps=gaps,
        misconception_codes=misconceptions,
        prerequisite_hypothesis_ids=[],
        source_attempt_ids=attempt_ids,
        evidence_event_ids=[],
        policy_version=MASTERY_POLICY_VERSION,
    )