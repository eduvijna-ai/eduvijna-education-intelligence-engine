from __future__ import annotations

import math
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
class SingleCorrectScoreRule:
    correct_marks: float
    incorrect_penalty: float


@dataclass(frozen=True, slots=True)
class MultiSelectScoreRule:
    full_marks: float
    partial_marks: float
    negative_marks: float
    allow_proper_subset_partial: bool = True


@dataclass(frozen=True, slots=True)
class NumericalScoreRule:
    full_marks: float
    negative_marks: float
    tolerance: float
    significant_digits: int | None = None


def validate_numerical_rule(rule: NumericalScoreRule) -> bool:
    if not math.isfinite(rule.full_marks) or rule.full_marks < 0:
        return False
    if not math.isfinite(rule.negative_marks) or rule.negative_marks < 0:
        return False
    if not math.isfinite(rule.tolerance) or rule.tolerance < 0:
        return False
    if rule.significant_digits is not None and rule.significant_digits < 0:
        return False
    return True


def score_single_correct(
    *,
    selected: str | None,
    correct: str,
    rule: SingleCorrectScoreRule,
) -> tuple[float, ScoreOutcome]:
    if selected is None or selected == "":
        return 0.0, ScoreOutcome.BLANK
    if selected == correct:
        return rule.correct_marks, ScoreOutcome.CORRECT
    return -rule.incorrect_penalty, ScoreOutcome.INCORRECT


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

    wrong_options = selected - correct
    if wrong_options:
        return -rule.negative_marks, ScoreOutcome.INCORRECT

    if (
        rule.allow_proper_subset_partial
        and selected
        and selected.issubset(correct)
        and selected != correct
    ):
        return rule.partial_marks, ScoreOutcome.PARTIAL

    return -rule.negative_marks, ScoreOutcome.INCORRECT


def score_numerical(
    *,
    submitted: float | None,
    expected: float,
    rule: NumericalScoreRule,
) -> tuple[float, ScoreOutcome]:
    if not validate_numerical_rule(rule):
        return 0.0, ScoreOutcome.REVIEW_REQUIRED
    if submitted is None:
        return 0.0, ScoreOutcome.BLANK
    if not math.isfinite(submitted) or not math.isfinite(expected):
        return 0.0, ScoreOutcome.REVIEW_REQUIRED

    rounded_submitted = submitted
    if rule.significant_digits is not None:
        rounded_submitted = round(submitted, rule.significant_digits)

    if abs(rounded_submitted - expected) <= rule.tolerance:
        return rule.full_marks, ScoreOutcome.CORRECT
    return -rule.negative_marks, ScoreOutcome.INCORRECT


def build_scoring_preview(rules: dict[str, Any]) -> dict[str, Any]:
    """Serialize paper-specific rules for audit without inventing defaults."""

    return {"rules": rules, "source_pinned": bool(rules)}
