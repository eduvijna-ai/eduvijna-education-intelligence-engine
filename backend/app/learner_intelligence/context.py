from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.enums import IssueCode
from app.models.learner_intelligence import AssessmentAttempt


def resolve_trusted_learner_context(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
) -> tuple[TrustedActorContext | None, IssueCode | None]:
    _ = (session, organization_id, institution_id, learner_id)
    if not runtime_learner_db_io_allowed():
        return None, containment_issue()
    return None, containment_issue()


def authorize_actor(session: Session, actor: TrustedActorContext) -> IssueCode | None:
    _ = (session, actor)
    if not runtime_learner_db_io_allowed():
        return containment_issue()
    return containment_issue()


def load_bound_attempt(
    session: Session,
    actor: TrustedActorContext,
    attempt_id: str,
) -> tuple[AssessmentAttempt | None, IssueCode | None]:
    _ = (session, actor, attempt_id)
    if not runtime_learner_db_io_allowed():
        return None, containment_issue()
    return None, containment_issue()