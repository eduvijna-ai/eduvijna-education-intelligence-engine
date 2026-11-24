from __future__ import annotations

from typing import Any

from app.learner_intelligence.enums import MasteryLevel
from app.models.learner_intelligence import ConceptMasteryRecord, ScoreEvidenceEvent


def topic_rollup(
    events: list[ScoreEvidenceEvent],
    *,
    topic_concepts: dict[str, list[str]],
) -> dict[str, Any]:
    """D15-20: denominators = mapped concepts; no double count within item."""

    rollups: dict[str, Any] = {}
    for topic, concepts in topic_concepts.items():
        concept_set = set(concepts)
        correct = 0
        incorrect = 0
        observed_concepts: set[str] = set()
        for ev in events:
            tagged = [c for c in (ev.concept_codes_json or []) if c in concept_set]
            if not tagged:
                continue
            for code in tagged:
                observed_concepts.add(code)
            if ev.verdict == "correct":
                correct += 1
            elif ev.verdict in ("incorrect", "partial"):
                incorrect += 1
        rollups[topic] = {
            "mapped_concepts": len(concept_set),
            "observed_concepts": len(observed_concepts),
            "coverage_ratio": len(observed_concepts) / len(concept_set) if concept_set else 0,
            "support_correct": correct,
            "support_incorrect": incorrect,
        }
    return rollups


def exam_performance_isolation(
    attempts_meta: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """D15-23: group by exam_pack + version + performance_mode."""

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in attempts_meta:
        key = "|".join(
            [
                str(row.get("exam_pack_code") or "none"),
                str(row.get("exam_version_id") or "none"),
                str(row.get("performance_mode") or "practice"),
            ]
        )
        buckets.setdefault(key, []).append(row)
    return buckets


def cognitive_performance(
    mastery_rows: list[ConceptMasteryRecord],
    concept_cognitive: dict[str, str],
) -> dict[str, Any]:
    """D15-21: Bloom/cognitive dimension from Day6-style mapping."""

    buckets: dict[str, list[str]] = {}
    for row in mastery_rows:
        tag = concept_cognitive.get(row.concept_code, "UNCLASSIFIED")
        buckets.setdefault(tag, []).append(row.mastery_level)
    summary: dict[str, Any] = {}
    for tag, levels in buckets.items():
        secure = sum(1 for lv in levels if lv == MasteryLevel.SECURE.value)
        summary[tag] = {"count": len(levels), "secure_count": secure}
    return summary