from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.learner_intelligence.contracts import ItemScoreOutcome, RecordResponseRequest, SnapshotItem
from app.learner_intelligence.enums import ResponseKind, ScoringVerdict

_PARTIAL_POLICY = "scoring@v1-multi_partial"


def _finite_decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not dec.is_finite():
        return None
    return dec


def _dec(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def score_item_response(
    item: SnapshotItem,
    request: RecordResponseRequest,
) -> ItemScoreOutcome:
    """D15-10..13: server-side scoring from trusted snapshot only."""

    max_marks = _finite_decimal(item.marks_if_correct)
    if max_marks is None:
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.REVIEW_REQUIRED,
            marks_awarded=Decimal("0"),
            max_marks=Decimal("0"),
        )
    if request.response_kind == ResponseKind.UNANSWERED:
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.BLANK,
            marks_awarded=item.marks_if_blank,
            max_marks=max_marks,
        )
    if request.response_kind == ResponseKind.DESCRIPTIVE:
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.REVIEW_REQUIRED,
            marks_awarded=Decimal("0"),
            max_marks=max_marks,
        )
    qtype = item.question_type
    if qtype == "single_choice":
        single = request.response_kind == ResponseKind.SINGLE_CHOICE
        if not single or len(request.selected_option_keys) != 1:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.REVIEW_REQUIRED,
                marks_awarded=Decimal("0"),
                max_marks=max_marks,
            )
        key = request.selected_option_keys[0]
        correct_keys = {o.option_key for o in item.options if o.is_correct}
        if key in correct_keys:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.CORRECT,
                marks_awarded=item.marks_if_correct,
                max_marks=max_marks,
            )
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.INCORRECT,
            marks_awarded=item.marks_if_incorrect,
            max_marks=max_marks,
        )
    if qtype == "multi_select":
        if request.response_kind != ResponseKind.MULTI_SELECT:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.REVIEW_REQUIRED,
                marks_awarded=Decimal("0"),
                max_marks=max_marks,
            )
        correct = {o.option_key for o in item.options if o.is_correct}
        selected = set(request.selected_option_keys)
        if selected == correct:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.CORRECT,
                marks_awarded=item.marks_if_correct,
                max_marks=max_marks,
            )
        if item.scoring_policy_version == _PARTIAL_POLICY:
            if selected & correct:
                return ItemScoreOutcome(
                    item_sequence=item.item_sequence,
                    verdict=ScoringVerdict.PARTIAL,
                    marks_awarded=item.marks_if_incorrect,
                    max_marks=max_marks,
                )
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.INCORRECT,
            marks_awarded=item.marks_if_incorrect,
            max_marks=max_marks,
        )
    if qtype == "numeric":
        if request.response_kind != ResponseKind.NUMERIC or request.numeric_value is None:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.REVIEW_REQUIRED,
                marks_awarded=Decimal("0"),
                max_marks=max_marks,
            )
        if item.numeric_answer is None:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.REVIEW_REQUIRED,
                marks_awarded=Decimal("0"),
                max_marks=max_marks,
            )
        answer = _finite_decimal(item.numeric_answer)
        given = _finite_decimal(request.numeric_value)
        tol = _finite_decimal(item.numeric_tolerance) or Decimal("0")
        if answer is None or given is None:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.REVIEW_REQUIRED,
                marks_awarded=Decimal("0"),
                max_marks=max_marks,
            )
        if abs(given - answer) <= tol:
            return ItemScoreOutcome(
                item_sequence=item.item_sequence,
                verdict=ScoringVerdict.CORRECT,
                marks_awarded=item.marks_if_correct,
                max_marks=max_marks,
            )
        return ItemScoreOutcome(
            item_sequence=item.item_sequence,
            verdict=ScoringVerdict.INCORRECT,
            marks_awarded=item.marks_if_incorrect,
            max_marks=max_marks,
        )
    return ItemScoreOutcome(
        item_sequence=item.item_sequence,
        verdict=ScoringVerdict.REVIEW_REQUIRED,
        marks_awarded=Decimal("0"),
        max_marks=max_marks,
    )


def aggregate_attempt_marks(outcomes: list[ItemScoreOutcome]) -> tuple[Decimal, Decimal]:
    total = Decimal("0")
    max_total = Decimal("0")
    for row in outcomes:
        total += row.marks_awarded
        max_total += row.max_marks
    return total, max_total