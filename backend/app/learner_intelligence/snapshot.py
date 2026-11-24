from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation

from app.learner_intelligence.contracts import SnapshotItem
from app.learner_intelligence.enums import IssueCode


def _canonical_item_payload(item: SnapshotItem) -> dict[str, object]:
    return {
        "item_sequence": item.item_sequence,
        "question_id": item.question_id,
        "stem_text": item.stem_text,
        "question_type": item.question_type,
        "options": [
            {
                "option_key": o.option_key,
                "display_text": o.display_text,
                "is_correct": o.is_correct,
            }
            for o in item.options
        ],
        "marks_if_correct": str(item.marks_if_correct),
        "marks_if_incorrect": str(item.marks_if_incorrect),
        "marks_if_blank": str(item.marks_if_blank),
        "numeric_answer": item.numeric_answer,
        "numeric_tolerance": str(item.numeric_tolerance) if item.numeric_tolerance else None,
        "concept_codes": sorted(item.concept_codes),
        "learning_outcome_ids": sorted(item.learning_outcome_ids),
        "competency_codes": sorted(item.competency_codes),
        "difficulty_band": item.difficulty_band,
        "cognitive_level": item.cognitive_level,
        "scoring_policy_version": item.scoring_policy_version,
        "source_version": item.source_version,
        "diagnostic_tags_json": item.diagnostic_tags_json,
    }


def compute_item_fingerprint(item: SnapshotItem) -> str:
    payload = _canonical_item_payload(item)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_assessment_fingerprint(items: list[SnapshotItem]) -> str:
    ordered = sorted(items, key=lambda i: i.item_sequence)
    parts = [compute_item_fingerprint(item) for item in ordered]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def validate_items_structure(items: list[SnapshotItem]) -> IssueCode | None:
    sequences = [item.item_sequence for item in items]
    if len(sequences) != len(set(sequences)):
        return IssueCode.DUPLICATE_RESPONSE
    qids = [item.question_id for item in items]
    if len(qids) != len(set(qids)):
        return IssueCode.DUPLICATE_RESPONSE
    for item in items:
        try:
            if item.marks_if_correct <= Decimal("0"):
                return IssueCode.UNSUPPORTED_POLICY
            if item.marks_if_blank > item.marks_if_correct:
                return IssueCode.UNSUPPORTED_POLICY
        except (InvalidOperation, TypeError):
            return IssueCode.UNSUPPORTED_POLICY
        keys = [o.option_key for o in item.options]
        if len(keys) != len(set(keys)):
            return IssueCode.UNKNOWN_OPTION
    return None


def canonicalize_items(items: list[SnapshotItem]) -> list[dict[str, object]]:
    return [_canonical_item_payload(item) for item in sorted(items, key=lambda i: i.item_sequence)]


def verify_item_matches_persisted_row(
    item: SnapshotItem,
    *,
    row_fingerprint: str,
    row_marks_correct: Decimal,
    row_marks_incorrect: Decimal,
    row_marks_blank: Decimal,
    policy_version: str,
) -> bool:
    if compute_item_fingerprint(item) != row_fingerprint:
        return False
    if Decimal(str(item.marks_if_correct)) != Decimal(str(row_marks_correct)):
        return False
    if Decimal(str(item.marks_if_incorrect)) != Decimal(str(row_marks_incorrect)):
        return False
    if Decimal(str(item.marks_if_blank)) != Decimal(str(row_marks_blank)):
        return False
    return item.scoring_policy_version == policy_version


def learner_facing_snapshot(item: SnapshotItem, *, snapshot_row_id: str) -> dict[str, object]:
    """D15-07: no answer-bearing fingerprint in learner read model."""

    return {
        "item_sequence": item.item_sequence,
        "issued_snapshot_id": snapshot_row_id,
        "question_id": item.question_id,
        "stem_text": item.stem_text,
        "question_type": item.question_type,
        "options": [
            {"option_key": o.option_key, "display_text": o.display_text} for o in item.options
        ],
        "marks_if_correct": str(item.marks_if_correct),
        "marks_if_incorrect": str(item.marks_if_incorrect),
        "marks_if_blank": str(item.marks_if_blank),
    }