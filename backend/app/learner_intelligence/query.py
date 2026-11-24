from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.enums import IssueCode


def list_attempts_for_learner(
    session: Session,
    actor: TrustedActorContext,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], list[IssueCode]]:
    _ = (session, actor, limit, offset)
    if not runtime_learner_db_io_allowed():
        return [], [containment_issue()]
    return [], [containment_issue()]


def read_mastery_summary(
    session: Session,
    actor: TrustedActorContext,
) -> tuple[list[dict[str, Any]], list[IssueCode]]:
    _ = (session, actor)
    if not runtime_learner_db_io_allowed():
        return [], [containment_issue()]
    return [], [containment_issue()]


def read_responses_redacted(
    session: Session,
    actor: TrustedActorContext,
    attempt_id: str,
) -> tuple[list[dict[str, Any]], list[IssueCode]]:
    _ = (session, actor, attempt_id)
    if not runtime_learner_db_io_allowed():
        return [], [containment_issue()]
    return [], [containment_issue()]


def read_diagnostic_events(
    session: Session,
    actor: TrustedActorContext,
) -> tuple[list[dict[str, Any]], list[IssueCode]]:
    _ = (session, actor)
    if not runtime_learner_db_io_allowed():
        return [], [containment_issue()]
    return [], [containment_issue()]