from __future__ import annotations

import hashlib
import json

from app.learner_intelligence.contracts import SnapshotItem


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
        "concept_codes": item.concept_codes,
        "scoring_policy_version": item.scoring_policy_version,
        "source_version": item.source_version,
    }


def compute_item_fingerprint(item: SnapshotItem) -> str:
    payload = _canonical_item_payload(item)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_assessment_fingerprint(items: list[SnapshotItem]) -> str:
    ordered = sorted(items, key=lambda i: i.item_sequence)
    parts = [compute_item_fingerprint(item) for item in ordered]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def learner_facing_snapshot(item: SnapshotItem) -> dict[str, object]:
    """D15-07: strip correct answers from learner read model."""

    return {
        "item_sequence": item.item_sequence,
        "question_id": item.question_id,
        "stem_text": item.stem_text,
        "question_type": item.question_type,
        "options": [
            {"option_key": o.option_key, "display_text": o.display_text} for o in item.options
        ],
        "marks_if_correct": str(item.marks_if_correct),
        "marks_if_incorrect": str(item.marks_if_incorrect),
        "marks_if_blank": str(item.marks_if_blank),
        "content_fingerprint": compute_item_fingerprint(item),
    }