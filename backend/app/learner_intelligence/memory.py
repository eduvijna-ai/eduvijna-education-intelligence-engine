from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learner_intelligence import LearnerMemoryEntry, ScoreEvidenceEvent


def append_memory_from_event(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
    memory_key: str,
    event: ScoreEvidenceEvent,
    payload: dict[str, Any],
) -> LearnerMemoryEntry:
    """D15-28/29: versioned entries with provenance; no silent overwrite."""

    last_version = session.scalar(
        select(LearnerMemoryEntry.entry_version)
        .where(
            LearnerMemoryEntry.learner_id == learner_id,
            LearnerMemoryEntry.memory_key == memory_key,
        )
        .order_by(LearnerMemoryEntry.entry_version.desc())
        .limit(1)
    )
    version = int(last_version or 0) + 1
    entry = LearnerMemoryEntry(
        organization_id=organization_id,
        learner_id=learner_id,
        memory_key=memory_key,
        entry_version=version,
        payload_json=payload,
        source_event_id=str(event.id),
        retracted=False,
    )
    session.add(entry)
    return entry


def rebuild_memory_keys(
    session: Session,
    *,
    organization_id: str,
    learner_id: str,
) -> list[str]:
    events = list(
        session.scalars(
            select(ScoreEvidenceEvent)
            .where(
                ScoreEvidenceEvent.organization_id == organization_id,
                ScoreEvidenceEvent.learner_id == learner_id,
            )
            .order_by(ScoreEvidenceEvent.created_at)
        ).all()
    )
    keys: list[str] = []
    for ev in events:
        key = f"score:{ev.attempt_id}:{ev.item_sequence}"
        append_memory_from_event(
            session,
            organization_id=ev.organization_id,
            learner_id=learner_id,
            memory_key=key,
            event=ev,
            payload={
                "verdict": ev.verdict,
                "marks_awarded": str(ev.marks_awarded),
                "rebuilt_at": datetime.now(UTC).isoformat(),
            },
        )
        keys.append(key)
    return keys