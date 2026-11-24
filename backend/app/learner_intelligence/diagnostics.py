from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.learner_intelligence.containment import runtime_learner_db_io_allowed
from app.learner_intelligence.contracts import ItemScoreOutcome, SnapshotItem
from app.learner_intelligence.enums import ScoringVerdict
from app.learner_intelligence.harness import TRUSTED_DIAGNOSTIC_EVIDENCE_REF
from app.models.learner_intelligence import DiagnosticProfileEvent


def _tags_from_snapshot(item: SnapshotItem) -> list[OptionDiagnosticTag]:
    tags: list[OptionDiagnosticTag] = []
    for raw in item.diagnostic_tags_json:
        tags.append(OptionDiagnosticTag.model_validate(raw))
    return tags


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
    """D15-24..27: containment — no runtime persistence."""

    if not runtime_learner_db_io_allowed():
        return []
    if score.verdict == ScoringVerdict.CORRECT:
        return []
    tags = _tags_from_snapshot(item)
    events: list[DiagnosticProfileEvent] = []
    for key in selected_option_keys:
        match = next((t for t in tags if t.option_key == key), None)
        if match is None or match.is_correct:
            continue
        if match.validation_status != DiagnosticValidationStatus.PASS:
            continue
        if not match.misconception_code:
            continue
        if TRUSTED_DIAGNOSTIC_EVIDENCE_REF not in (match.evidence_refs or []):
            continue
        event = DiagnosticProfileEvent(
            organization_id=organization_id,
            learner_id=learner_id,
            attempt_id=attempt_id,
            response_id=response_id,
            item_sequence=item.item_sequence,
            option_key=key,
            misconception_code=match.misconception_code,
            taxonomy_version=match.taxonomy_version,
            severity=None,
            confidence="low",
            hypothesis_only=True,
            metadata_json={
                "error_pattern": match.error_pattern,
                "diagnostic_signal": match.diagnostic_signal,
                "prerequisite_hypothesis": "NOT_READY",
                "day10_integration": "NOT_READY",
            },
        )
        session.add(event)
        events.append(event)
    return events


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