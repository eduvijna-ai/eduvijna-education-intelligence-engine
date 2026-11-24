from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import DAY16_HANDOFF_READINESS
from app.learner_intelligence.contracts import RemediationHandoff, TrustedActorContext
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION


def _blocked_handoff() -> RemediationHandoff:
    return RemediationHandoff(
        readiness="NOT_READY",
        learner_id="",
        organization_id="",
        institution_id="",
        concept_gaps=[],
        misconception_codes=[],
        prerequisite_hypothesis_ids=[],
        source_attempt_ids=[],
        evidence_event_ids=[],
        policy_version=MASTERY_POLICY_VERSION,
        actionable=False,
        synthetic_diagnostic_only=False,
    )


def build_day16_handoff(
    session: Session,
    actor: TrustedActorContext,
) -> RemediationHandoff:
    _ = (session, actor)
    assert DAY16_HANDOFF_READINESS is False
    return _blocked_handoff()


def build_synthetic_diagnostic_handoff(
    session: Session,
    actor: TrustedActorContext,
) -> RemediationHandoff:
    _ = (session, actor)
    return _blocked_handoff().model_copy(update={"synthetic_diagnostic_only": True})