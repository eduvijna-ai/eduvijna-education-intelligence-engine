"""Pure in-memory Day15 diagnostic calculations (no database I/O)."""

from __future__ import annotations

from decimal import Decimal

from app.learner_intelligence.contracts import RecordResponseRequest, TrustedActorContext
from app.learner_intelligence.enums import ResponseKind
from app.learner_intelligence.harness import build_two_item_catalog_items
from app.learner_intelligence.scoring import aggregate_attempt_marks, score_item_response


def pure_missing_item_scoring_diagnostic() -> dict[str, str]:
    """Example: one answered item, one blank → 4/8 max (synthetic calculation only)."""

    items = build_two_item_catalog_items()
    synthetic_actor = TrustedActorContext(
        organization_id="synthetic",
        institution_id="synthetic",
        learner_id="synthetic",
    )
    answered = score_item_response(
        items[0],
        RecordResponseRequest(
            actor=synthetic_actor,
            attempt_id="synthetic-diagnostic",
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["B"],
        ),
    )
    blank = score_item_response(
        items[1],
        RecordResponseRequest(
            actor=synthetic_actor,
            attempt_id="synthetic-diagnostic",
            item_sequence=2,
            response_kind=ResponseKind.UNANSWERED,
        ),
    )
    total, max_marks = aggregate_attempt_marks([answered, blank])
    return {
        "label": "synthetic_calculation_only",
        "total_marks": str(total),
        "max_marks": str(max_marks),
        "persisted": "false",
    }


def pure_full_correct_scoring_diagnostic() -> dict[str, str]:
    items = build_two_item_catalog_items()
    synthetic_actor = TrustedActorContext(
        organization_id="synthetic",
        institution_id="synthetic",
        learner_id="synthetic",
    )
    first = score_item_response(
        items[0],
        RecordResponseRequest(
            actor=synthetic_actor,
            attempt_id="synthetic-diagnostic",
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["B"],
        ),
    )
    second = score_item_response(
        items[1],
        RecordResponseRequest(
            actor=synthetic_actor,
            attempt_id="synthetic-diagnostic",
            item_sequence=2,
            response_kind=ResponseKind.NUMERIC,
            numeric_value="7",
        ),
    )
    total, max_marks = aggregate_attempt_marks([first, second])
    assert total == Decimal("8")
    assert max_marks == Decimal("8")
    return {
        "label": "synthetic_calculation_only",
        "total_marks": str(total),
        "max_marks": str(max_marks),
        "persisted": "false",
    }