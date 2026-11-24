from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.context import authorize_actor
from app.learner_intelligence.contracts import RemediationHandoff, TrustedActorContext
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION
from app.learner_intelligence.gate import require_harness_or_blocked
from app.learner_intelligence.harness_runtime import harness_session_authorized


def build_day16_handoff(
    session: Session,
    actor: TrustedActorContext,
) -> RemediationHandoff:
    """Production handoff remains NOT_READY until Day16 separately approved (D15 R3-05)."""

    empty = RemediationHandoff(
        readiness="NOT_READY",
        learner_id=actor.learner_id,
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        policy_version=MASTERY_POLICY_VERSION,
        concept_gaps=[],
        misconception_codes=[],
        prerequisite_hypothesis_ids=[],
        source_attempt_ids=[],
        evidence_event_ids=[],
        actionable=False,
        synthetic_diagnostic_only=False,
    )

    if require_harness_or_blocked(session) is not None:
        return empty
    if authorize_actor(session, actor) is not None:
        return empty

    return empty.model_copy(
        update={
            "synthetic_diagnostic_only": harness_session_authorized(session),
        }
    )


def build_synthetic_diagnostic_handoff(
    session: Session,
    actor: TrustedActorContext,
) -> RemediationHandoff:
    """Explicit non-actionable diagnostic envelope for isolated harness demos only."""

    if require_harness_or_blocked(session) is not None:
        return build_day16_handoff(session, actor)
    if authorize_actor(session, actor) is not None:
        return build_day16_handoff(session, actor)
    return RemediationHandoff(
        readiness="NOT_READY",
        learner_id=actor.learner_id,
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        policy_version=MASTERY_POLICY_VERSION,
        concept_gaps=[],
        misconception_codes=[],
        prerequisite_hypothesis_ids=[],
        source_attempt_ids=[],
        evidence_event_ids=[],
        actionable=False,
        synthetic_diagnostic_only=True,
    )