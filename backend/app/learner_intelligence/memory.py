from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import runtime_learner_db_io_allowed
from app.models.learner_intelligence import LearnerMemoryEntry, ScoreEvidenceEvent


def append_memory_from_event(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
    memory_key: str,
    event: ScoreEvidenceEvent,
    payload: dict[str, Any],
) -> LearnerMemoryEntry | None:
    _ = (session, organization_id, learner_id, memory_key, event, payload)
    if not runtime_learner_db_io_allowed():
        return None
    return None


def rebuild_memory_keys(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
) -> list[str]:
    _ = (session, organization_id, learner_id)
    if not runtime_learner_db_io_allowed():
        return []
    return []