from decimal import Decimal

from app.learner_intelligence.contracts import (
    RecordResponseRequest,
    SnapshotItem,
    SnapshotOption,
    TrustedActorContext,
)
from app.learner_intelligence.enums import ResponseKind
from app.learner_intelligence.scoring import aggregate_attempt_marks, score_item_response


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        organization_id="org",
        institution_id="inst",
        learner_id="learner",
    )


def test_decimal_scoring_single_and_numeric() -> None:
    item = SnapshotItem(
        item_sequence=1,
        question_id="q1",
        stem_text="stem",
        question_type="single_choice",
        options=[
            SnapshotOption(option_key="A", display_text="x", is_correct=True),
            SnapshotOption(option_key="B", display_text="y", is_correct=False),
        ],
        marks_if_correct=Decimal("4"),
        marks_if_incorrect=Decimal("-1"),
        source_version="synthetic@v1",
        content_fingerprint="fp",
    )
    req = RecordResponseRequest(
        actor=_actor(),
        attempt_id="a1",
        item_sequence=1,
        response_kind=ResponseKind.SINGLE_CHOICE,
        selected_option_keys=["A"],
    )
    out = score_item_response(item, req)
    assert out.marks_awarded == Decimal("4")
    total, max_m = aggregate_attempt_marks([out])
    assert total == Decimal("4")
    assert max_m == Decimal("4")


def test_descriptive_review_required() -> None:
    item = SnapshotItem(
        item_sequence=1,
        question_id="q1",
        stem_text="stem",
        question_type="descriptive",
        marks_if_correct=Decimal("10"),
        marks_if_incorrect=Decimal("0"),
        source_version="synthetic@v1",
        content_fingerprint="fp",
    )
    req = RecordResponseRequest(
        actor=_actor(),
        attempt_id="a1",
        item_sequence=1,
        response_kind=ResponseKind.DESCRIPTIVE,
        descriptive_text="answer",
    )
    out = score_item_response(item, req)
    assert out.verdict.value == "review_required"