from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import containment_issue, runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import (
    AttemptOutcome,
    CreateAttemptRequest,
    FinalizeAttemptRequest,
    RecordResponseRequest,
    TrustedActorContext,
)
from app.learner_intelligence.enums import IssueCode
from app.learner_intelligence.gate import blocked_outcome
from app.models.learner_intelligence import AssessmentAttempt


class LearnerIntelligenceService:
    """Day 15 — containment: no runtime learner DB I/O."""

    def create_attempt(
        self,
        session: Session,
        request: CreateAttemptRequest,
    ) -> tuple[AssessmentAttempt | None, AttemptOutcome]:
        _ = (session, request)
        if runtime_learner_db_io_allowed():
            pass
        return None, blocked_outcome(code=containment_issue())

    def learner_view_items(
        self,
        session: Session,
        actor: TrustedActorContext,
        attempt_id: str,
    ) -> tuple[list[dict[str, object]], list[IssueCode]]:
        _ = (session, actor, attempt_id)
        return [], [containment_issue()]

    def record_response(
        self,
        session: Session,
        request: RecordResponseRequest,
    ) -> tuple[bool, list[IssueCode]]:
        _ = (session, request)
        return False, [containment_issue()]

    def finalize(
        self,
        session: Session,
        request: FinalizeAttemptRequest,
    ) -> AttemptOutcome:
        _ = (session, request)
        return blocked_outcome(attempt_id=request.attempt_id, code=containment_issue())

    def abandon(
        self,
        session: Session,
        actor: TrustedActorContext,
        attempt_id: str,
    ) -> list[IssueCode]:
        _ = (session, actor, attempt_id)
        return [containment_issue()]
