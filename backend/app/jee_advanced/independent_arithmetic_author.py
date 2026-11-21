"""Day12 test-local author draft from visible arithmetic stem/options only."""

from __future__ import annotations

from typing import Any

from app.jee_advanced.independent_arithmetic_solver import propose_answer_from_display


def author_draft_from_display(
    *,
    item_id: str,
    display: dict[str, Any],
    revision_id: str,
    learning_outcome_id: str | None,
) -> dict[str, Any] | None:
    """Build an author item with exactly one correct flag derived from stem math."""

    correct_key = propose_answer_from_display(display)
    if not correct_key:
        return None
    options: list[dict[str, Any]] = []
    for idx, raw in enumerate(list(display.get("options") or [])):
        if not isinstance(raw, dict):
            continue
        opt_key = str(raw.get("option_key") or "").strip()
        options.append(
            {
                "option_key": opt_key,
                "text": str(raw.get("text") or ""),
                "is_correct": opt_key == correct_key,
                "sequence": raw.get("sequence") or idx + 1,
            }
        )
    if not options:
        return None
    return {
        "item_id": item_id,
        "stem_text": str(display.get("stem_text") or ""),
        "question_type": str(display.get("question_type") or "single_choice"),
        "options": options,
        "answer_json": {"option_key": correct_key},
        "marks": 1.0,
        "source_revision_ids": [revision_id],
        "learning_outcome_ids": [learning_outcome_id] if learning_outcome_id else [],
        "competency_codes": ["application"],
        "declared_cognitive_level": "Apply",
        "declared_difficulty": 2,
        "metadata_json": {"arithmetic_independent_author": True},
    }