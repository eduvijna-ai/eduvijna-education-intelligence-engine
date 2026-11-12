from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ScoreOutcome(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    BLANK = "blank"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class MultiSelectScoreRule:
    full_marks: float
    partial_marks: float
    negative_marks: float


@dataclass(frozen=True, slots=True)
class NumericalScoreRule:
    full_marks: float
    negative_marks: float
    tolerance: float
    significant_digits: int | None = None


def score_single_correct(
    *,
    selected: str | None,
    correct: str,
    rule_marks: float,
) -> tuple[float, ScoreOutcome]:
    if selected is None or selected == "":
        return 0.0, ScoreOutcome.BLANK
    if selected == correct:
        return rule_marks, ScoreOutcome.CORRECT
    return -rule_marks, ScoreOutcome.INCORRECT


def score_multi_select(
    *,
    selected: set[str],
    correct: set[str],
    rule: MultiSelectScoreRule,
) -> tuple[float, ScoreOutcome]:
    if not selected:
        return 0.0, ScoreOutcome.BLANK
    if selected == correct:
        return rule.full_marks, ScoreOutcome.CORRECT
    if selected.issubset(correct) and selected:
        return rule.partial_marks, ScoreOutcome.PARTIAL
    if selected & correct:
        return rule.partial_marks, ScoreOutcome.PARTIAL
    return -rule.negative_marks, ScoreOutcome.INCORRECT


def score_numerical(
    *,
    submitted: float | None,
    expected: float,
    rule: NumericalScoreRule,
) -> tuple[float, ScoreOutcome]:
    if submitted is None:
        return 0.0, ScoreOutcome.BLANK
    if abs(submitted - expected) <= rule.tolerance:
        return rule.full_marks, ScoreOutcome.CORRECT
    return -rule.negative_marks, ScoreOutcome.INCORRECT


def build_scoring_preview(rules: dict[str, Any]) -> dict[str, Any]:
    """Serialize paper-specific rules for audit without inventing defaults."""

    return {"rules": rules, "source_pinned": bool(rules)}
