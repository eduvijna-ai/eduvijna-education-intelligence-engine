import math

from app.jee_advanced.scoring import (
    MultiSelectScoreRule,
    NumericalScoreRule,
    ScoreOutcome,
    SingleCorrectScoreRule,
    build_scoring_preview,
    round_to_significant_figures,
    score_multi_select,
    score_numerical,
    score_single_correct,
    validate_numerical_rule,
)


def test_multi_select_proper_subset_partial() -> None:
    rule = MultiSelectScoreRule(full_marks=4.0, partial_marks=2.0, negative_marks=2.0)
    marks, outcome = score_multi_select(
        selected={"A", "B"},
        correct={"A", "B", "C"},
        rule=rule,
    )
    assert outcome == ScoreOutcome.PARTIAL
    assert marks == 2.0


def test_multi_select_wrong_extra_never_partial() -> None:
    rule = MultiSelectScoreRule(full_marks=4.0, partial_marks=2.0, negative_marks=2.0)
    marks, outcome = score_multi_select(
        selected={"A", "D"},
        correct={"A", "B"},
        rule=rule,
    )
    assert outcome == ScoreOutcome.INCORRECT
    assert marks == -2.0


def test_single_correct_uses_explicit_penalty() -> None:
    rule = SingleCorrectScoreRule(correct_marks=3.0, incorrect_penalty=1.0)
    marks, outcome = score_single_correct(selected="Z", correct="A", rule=rule)
    assert outcome == ScoreOutcome.INCORRECT
    assert marks == -1.0


def test_numerical_malformed_rule_review() -> None:
    bad_rule = NumericalScoreRule(full_marks=3.0, negative_marks=1.0, tolerance=float("nan"))
    assert validate_numerical_rule(bad_rule) is False
    marks, outcome = score_numerical(submitted=1.0, expected=1.0, rule=bad_rule)
    assert outcome == ScoreOutcome.REVIEW_REQUIRED
    assert marks == 0.0


def test_numerical_non_finite_submission() -> None:
    rule = NumericalScoreRule(full_marks=3.0, negative_marks=1.0, tolerance=0.05)
    marks, outcome = score_numerical(submitted=math.inf, expected=2.0, rule=rule)
    assert outcome == ScoreOutcome.REVIEW_REQUIRED


def test_significant_figures_not_decimal_places() -> None:
    assert round_to_significant_figures(1234.5, 3) == 1230.0
    rule = NumericalScoreRule(
        full_marks=3.0,
        negative_marks=1.0,
        tolerance=5.0,
        significant_digits=3,
    )
    marks, outcome = score_numerical(submitted=1234.0, expected=1230.0, rule=rule)
    assert outcome == ScoreOutcome.CORRECT
    assert marks == 3.0


def test_scoring_preview_requires_approved_source() -> None:
    pinned = build_scoring_preview(
        {"full_marks": 4},
        approved_source_revision_id="rev-1",
        blueprint_rule_id="rule-1",
    )
    assert pinned["source_pinned"] is True
    unpinned = build_scoring_preview({"full_marks": 4})
    assert unpinned["source_pinned"] is False


def test_malformed_single_correct_rule_review() -> None:
    rule = SingleCorrectScoreRule(correct_marks=-1.0, incorrect_penalty=1.0)
    marks, outcome = score_single_correct(selected="A", correct="A", rule=rule)
    assert outcome == ScoreOutcome.REVIEW_REQUIRED
    assert marks == 0.0
