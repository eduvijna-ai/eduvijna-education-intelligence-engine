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


def round_to_significant_figures(value: float, sig_figs: int) -> float | None:
    if not math.isfinite(value) or sig_figs < 1:
        return None
    if value == 0:
        return 0.0
    magnitude = math.floor(math.log10(abs(value)))
    decimals = sig_figs - int(magnitude) - 1
    return round(value, decimals)


def validate_single_correct_rule(rule: SingleCorrectScoreRule) -> bool:
    return (
        math.isfinite(rule.correct_marks)
        and rule.correct_marks >= 0
        and math.isfinite(rule.incorrect_penalty)
        and rule.incorrect_penalty >= 0
    )


def validate_multi_select_rule(rule: MultiSelectScoreRule, *, correct: set[str]) -> bool:
    if not correct:
        return False
    return (
        math.isfinite(rule.full_marks)
        and rule.full_marks >= 0
        and math.isfinite(rule.partial_marks)
        and rule.partial_marks >= 0
        and rule.partial_marks <= rule.full_marks
        and math.isfinite(rule.negative_marks)
        and rule.negative_marks >= 0
    )


def validate_numerical_rule(rule: NumericalScoreRule) -> bool:
    if not math.isfinite(rule.full_marks) or rule.full_marks < 0:
        return False
    if not math.isfinite(rule.negative_marks) or rule.negative_marks < 0:
        return False
    if not math.isfinite(rule.tolerance) or rule.tolerance < 0:
        return False
    if rule.significant_digits is not None and rule.significant_digits < 1:
        return False
    return True


def score_single_correct(
    *,
    selected: str | None,
    correct: str,
    rule: SingleCorrectScoreRule,
) -> tuple[float, ScoreOutcome]:
    if not validate_single_correct_rule(rule):
        return 0.0, ScoreOutcome.REVIEW_REQUIRED
    if not correct:
        return 0.0, ScoreOutcome.REVIEW_REQUIRED
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
    if not validate_multi_select_rule(rule, correct=correct):
        return 0.0, ScoreOutcome.REVIEW_REQUIRED
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
        sig_rounded = round_to_significant_figures(submitted, rule.significant_digits)
        if sig_rounded is None:
            return 0.0, ScoreOutcome.REVIEW_REQUIRED
        rounded_submitted = sig_rounded

    if abs(rounded_submitted - expected) <= rule.tolerance:
        return rule.full_marks, ScoreOutcome.CORRECT
    return -rule.negative_marks, ScoreOutcome.INCORRECT


def build_scoring_preview(
    rules: dict[str, Any],
    *,
    session: Any | None = None,
    approved_source_revision_id: str | None = None,
    blueprint_rule_id: str | None = None,
    exam_version_id: str | None = None,
) -> dict[str, Any]:
    """Serialize scoring; official pinning requires a session-bound attestation path."""

    from sqlalchemy.orm import Session

    if (
        session is not None
        and isinstance(session, Session)
        and approved_source_revision_id
        and blueprint_rule_id
        and rules
    ):
        from app.jee_advanced.source_attested_scoring import build_attested_scoring_preview

        return build_attested_scoring_preview(
            session,
            rules=rules,
            approved_source_revision_id=approved_source_revision_id,
            blueprint_rule_id=blueprint_rule_id,
            exam_version_id=exam_version_id,
        )

    return {
        "rules": rules,
        "source_pinned": False,
        "demonstration_only": True,
        "approved_source_revision_id": approved_source_revision_id,
        "blueprint_rule_id": blueprint_rule_id,
    }
