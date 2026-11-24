from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.enums import IssueCode
from app.models import Institution, Learner, Organization
from app.models.learner_intelligence import AssessmentAttempt


def resolve_trusted_learner_context(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
) -> tuple[TrustedActorContext | None, IssueCode | None]:
    """D15-02: membership must exist in DB; caller cannot invent tenant binding."""

    if not runtime_learner_db_io_allowed():
        return None, containment_issue()

    org = session.get(Organization, organization_id)
    if org is None or not org.active:
        return None, IssueCode.OUT_OF_SCOPE
    inst = session.get(Institution, institution_id)
    if inst is None or not inst.active or str(inst.organization_id) != organization_id:
        return None, IssueCode.TENANT_MISMATCH
    learner = session.get(Learner, learner_id)
    if learner is None or not learner.active:
        return None, IssueCode.OUT_OF_SCOPE
    if str(learner.institution_id) != institution_id:
        return None, IssueCode.TENANT_MISMATCH
    return (
        TrustedActorContext(
            organization_id=organization_id,
            institution_id=institution_id,
            learner_id=learner_id,
        ),
        None,
    )


def authorize_actor(session: Session, actor: TrustedActorContext) -> IssueCode | None:
    trusted, err = resolve_trusted_learner_context(
        session,
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        learner_id=actor.learner_id,
    )
    if err is not None or trusted is None:
        return err or IssueCode.OUT_OF_SCOPE
    if (
        trusted.organization_id != actor.organization_id
        or trusted.institution_id != actor.institution_id
        or trusted.learner_id != actor.learner_id
    ):
        return IssueCode.TENANT_MISMATCH
    return None


def load_bound_attempt(
    session: Session,
    actor: TrustedActorContext,
    attempt_id: str,
) -> tuple[AssessmentAttempt | None, IssueCode | None]:
    _ = attempt_id
    if not runtime_learner_db_io_allowed():
        return None, containment_issue()
    if authorize_actor(session, actor) is not None:
        return None, IssueCode.TENANT_MISMATCH
    attempt = session.get(AssessmentAttempt, attempt_id)
    if attempt is None:
        return None, IssueCode.OUT_OF_SCOPE
    if str(attempt.organization_id) != actor.organization_id:
        return None, IssueCode.CROSS_TENANT
    if str(attempt.institution_id) != actor.institution_id:
        return None, IssueCode.TENANT_MISMATCH
    if str(attempt.learner_id) != actor.learner_id:
        return None, IssueCode.TENANT_MISMATCH
    if not attempt.synthetic_harness_only:
        return None, IssueCode.NOT_ELIGIBLE
    return attempt, None