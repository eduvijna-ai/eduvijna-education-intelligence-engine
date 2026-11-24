from decimal import Decimal

from app.ca_imat_eapcet.scoring import (
    score_ca_objective,
    score_eapcet,
    score_imat_decimal,
    validate_rubric_marks,
)


def test_ca_descriptive_rejects_objective_scoring() -> None:
    marks, issues = score_ca_objective(paper_code="paper1_accounting", correct=True, answered=True)
    assert marks == 0.0
    assert issues


def test_ca_objective_paper_scores() -> None:
    marks, issues = score_ca_objective(
        paper_code="paper3_quantitative_aptitude", correct=True, answered=True
    )
    assert marks == 1.0
    assert not issues


def test_imat_decimal_precision() -> None:
    val = score_imat_decimal(correct=True, answered=True)
    assert val == Decimal("1.5")


def test_eapcet_plus_one_zero() -> None:
    assert score_eapcet(correct=True, answered=True) == 1.0
    assert score_eapcet(correct=False, answered=True) == 0.0


def test_rubric_sum() -> None:
    ok, issues = validate_rubric_marks(
        criteria=[{"weight": 5}, {"weight": 5}],
        total_marks=10,
    )
    assert ok
    assert not issues