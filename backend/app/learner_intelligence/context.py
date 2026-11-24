from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.enums import IssueCode
from app.models import Institution, Learner


def resolve_trusted_learner_context(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
) -> tuple[TrustedActorContext | None, IssueCode | None]:
    """D15-02: membership must exist in DB; caller cannot invent tenant binding."""

    learner = session.get(Learner, learner_id)
    if learner is None or not learner.active:
        return None, IssueCode.OUT_OF_SCOPE
    if str(learner.institution_id) != institution_id:
        return None, IssueCode.TENANT_MISMATCH
    inst = session.get(Institution, institution_id)
    if inst is None or str(inst.organization_id) != organization_id:
        return None, IssueCode.TENANT_MISMATCH
    return (
        TrustedActorContext(
            organization_id=organization_id,
            institution_id=institution_id,
            learner_id=learner_id,
        ),
        None,
    )


def assert_learner_in_institution(session: Session, learner_id: str, institution_id: str) -> bool:
    row = session.scalar(
        select(Learner.id).where(
            Learner.id == learner_id,
            Learner.institution_id == institution_id,
            Learner.active.is_(True),
        )
    )
    return row is not None