from __future__ import annotations

from decimal import Decimal

from app.ca_imat_eapcet.constants import (
    CA_OBJECTIVE_NEGATIVE_MARK,
    CA_PAPER_CODES,
    CA_PAPER_KIND,
    EAPCET_MARK_BLANK,
    EAPCET_MARK_CORRECT,
    EAPCET_MARK_INCORRECT,
    IMAT_MARK_BLANK,
    IMAT_MARK_CORRECT,
    IMAT_MARK_INCORRECT,
)
from app.ca_imat_eapcet.enums import IssueCode


def score_ca_objective(
    *,
    paper_code: str,
    correct: bool,
    answered: bool,
) -> tuple[float, list[IssueCode]]:
    """D14-13: objective penalty only on papers 3/4; never on descriptive."""

    if paper_code not in CA_PAPER_CODES:
        return 0.0, [IssueCode.WRONG_PAPER]
    kind = CA_PAPER_KIND[paper_code]
    if kind == "descriptive":
        return 0.0, [IssueCode.CA_DESCRIPTIVE_ON_OBJECTIVE]
    if not answered:
        return 0.0, []
    if correct:
        return 1.0, []
    return float(CA_OBJECTIVE_NEGATIVE_MARK), []


def score_imat_decimal(*, correct: bool, answered: bool) -> Decimal:
    """D14-20: versioned decimal marks with blank handling."""

    if not answered:
        return Decimal(str(IMAT_MARK_BLANK))
    if correct:
        return Decimal(str(IMAT_MARK_CORRECT))
    return Decimal(str(IMAT_MARK_INCORRECT))


def score_eapcet(*, correct: bool, answered: bool) -> float:
    """D14-22: +1/0 pattern when source attested; synthetic uses same reference."""

    if not answered:
        return float(EAPCET_MARK_BLANK)
    if correct:
        return float(EAPCET_MARK_CORRECT)
    return float(EAPCET_MARK_INCORRECT)


def validate_rubric_marks(
    *,
    criteria: list[dict[str, object]],
    total_marks: float,
) -> tuple[bool, list[IssueCode]]:
    """D14-12: criteria weights must sum to total within bounds."""

    weight_sum = 0.0
    for c in criteria:
        w = c.get("weight")
        if isinstance(w, (int, float)):
            weight_sum += float(w)
    if abs(weight_sum - total_marks) > 0.01:
        return False, [IssueCode.CA_RUBRIC_INVALID]
    return True, []