from __future__ import annotations

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import ItemScoreOutcome
from app.learner_intelligence.enums import ScoringVerdict
from app.models.learner_intelligence import QuestionHistoryObservation


def record_history_observation(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
    attempt_id: str,
    question_id: str,
    item_sequence: int,
    source_version: str,
    score: ItemScoreOutcome,
) -> QuestionHistoryObservation | None:
    _ = (
        session,
        organization_id,
        learner_id,
        attempt_id,
        question_id,
        item_sequence,
        source_version,
        score,
    )
    if not runtime_learner_db_io_allowed():
        return None
    return None


def verdict_counts(observations: list[QuestionHistoryObservation]) -> dict[str, int]:
    counts = {v.value: 0 for v in ScoringVerdict}
    for obs in observations:
        if obs.verdict:
            counts[obs.verdict] = counts.get(obs.verdict, 0) + 1
    return counts