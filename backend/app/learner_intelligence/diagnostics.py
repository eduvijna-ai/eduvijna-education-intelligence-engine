from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.learner_intelligence.containment import runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import ItemScoreOutcome, SnapshotItem
from app.models.learner_intelligence import DiagnosticProfileEvent


def record_diagnostic_events(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    learner_id: str,
    attempt_id: str,
    item: SnapshotItem,
    selected_option_keys: list[str],
    score: ItemScoreOutcome,
    response_id: str | None = None,
) -> list[DiagnosticProfileEvent]:
    _ = (
        session,
        organization_id,
        institution_id,
        learner_id,
        attempt_id,
        item,
        selected_option_keys,
        score,
        response_id,
    )
    if not runtime_learner_db_io_allowed():
        return []
    return []


def aggregate_diagnostic_profile(events: list[DiagnosticProfileEvent]) -> dict[str, Any]:
    freq: dict[str, int] = {}
    attempts: list[str] = []
    for ev in events:
        freq[ev.misconception_code] = freq.get(ev.misconception_code, 0) + 1
        if ev.attempt_id not in attempts:
            attempts.append(ev.attempt_id)
    return {
        "misconception_frequencies": freq,
        "source_attempt_ids": attempts,
        "hypothesis_only": True,
        "day10_root_cause": "NOT_READY",
    }