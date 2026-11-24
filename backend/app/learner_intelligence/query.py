from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.privacy import redact_learner_payload
from app.models.learner_intelligence import (
    AssessmentAttempt,
    AttemptResponse,
    ConceptMasteryRecord,
    DiagnosticProfileEvent,
)


def list_attempts_for_learner(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """D15-30: internal tenant-scoped reads; no correct keys in responses."""

    rows = session.scalars(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.organization_id == organization_id,
            AssessmentAttempt.institution_id == institution_id,
            AssessmentAttempt.learner_id == learner_id,
        )
        .order_by(AssessmentAttempt.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        redact_learner_payload(
            {
                "attempt_id": str(r.id),
                "state": r.state,
                "assessment_key": r.assessment_key,
                "total_marks": str(r.total_marks) if r.total_marks is not None else None,
                "max_marks": str(r.max_marks) if r.max_marks is not None else None,
            }
        )
        for r in rows
    ]


def read_mastery_summary(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ConceptMasteryRecord).where(
            ConceptMasteryRecord.organization_id == organization_id,
            ConceptMasteryRecord.learner_id == learner_id,
        )
    ).all()
    return [
        {
            "concept_code": r.concept_code,
            "mastery_level": r.mastery_level,
            "confidence": r.confidence,
            "support_correct": r.support_correct,
            "support_incorrect": r.support_incorrect,
        }
        for r in rows
    ]


def read_responses_redacted(
    session: Session,
    attempt_id: str,
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(AttemptResponse).where(AttemptResponse.attempt_id == attempt_id)
    ).all()
    return [
        {
            "item_sequence": r.item_sequence,
            "response_kind": r.response_kind,
            "selected_option_keys": r.selected_option_keys_json,
            "is_final": r.is_final,
        }
        for r in rows
    ]


def read_diagnostic_events(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(DiagnosticProfileEvent).where(
            DiagnosticProfileEvent.organization_id == organization_id,
            DiagnosticProfileEvent.learner_id == learner_id,
        )
    ).all()
    return [
        {
            "misconception_code": r.misconception_code,
            "option_key": r.option_key,
            "attempt_id": r.attempt_id,
            "hypothesis_only": r.hypothesis_only,
        }
        for r in rows
    ]