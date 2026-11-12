from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.jee_main_exam_intelligence.fixtures import (
    build_practice_algebra_ten_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.question_pool import _answer_valid
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption


def _mcq(*, correct_option: str = "B", texts: tuple[str, ...] | None = None) -> Question:
    choices = texts or ("11", "12", "13", "14")
    question = Question(
        external_code="pool-trust-check",
        origin_type="teacher",
        question_type=QuestionType.MULTIPLE_CHOICE.value,
        stem_text="What is 7 + 5?",
        answer_json={"correct_option": correct_option},
        status=QuestionStatus.APPROVED.value,
        metadata_json={},
    )
    question.options = [
        QuestionOption(
            option_key=key,
            text=text,
            is_correct=key == "B",
        )
        for key, text in zip(("A", "B", "C", "D"), choices, strict=True)
    ]
    return question


def test_answer_pool_requires_consistent_option_key_and_unique_options() -> None:
    assert _answer_valid(_mcq())
    assert not _answer_valid(_mcq(correct_option="A"))
    assert not _answer_valid(_mcq(texts=("11", "12", "12", "14")))
    assert not _answer_valid(_mcq(texts=("11", "  ", "13", "14")))
    short = _mcq()
    short.options.pop()
    assert not _answer_valid(short)


@pytest.mark.parametrize(
    "value, accepted",
    [
        (12, True),
        (Decimal("12.5"), True),
        ("-3.25", True),
        (float("nan"), False),
        (float("inf"), False),
        ("Infinity", False),
        ("not-a-number", False),
        (True, False),
        (None, False),
    ],
)
def test_numeric_pool_rejects_nonfinite_unparseable_answer(
    value: object, accepted: bool
) -> None:
    question = Question(
        origin_type="teacher",
        question_type=QuestionType.NUMERICAL.value,
        stem_text="Enter a number",
        answer_json={"numeric_value": value},
        status=QuestionStatus.APPROVED.value,
    )
    assert _answer_valid(question) is accepted


def test_algebra_ten_rejects_tampered_approved_answer_pool() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ctx = seed_day11_fixture_context(session)
        algebra = [
            question for question in session.scalars(select(Question))
            if (question.metadata_json or {}).get("derived_topic_groups") == ["algebra"]
        ]
        assert len(algebra) >= 12
        for question in algebra[:3]:
            question.answer_json = {"correct_option": "D"}  # option A is marked correct
        session.commit()
        result = JeeMainExamIntelligenceService().plan_paper(
            session, build_practice_algebra_ten_request(ctx), persist=False
        )
        assert result.verdict == PaperPlanVerdict.FAIL
        assert result.actual_count < 10
        assert PaperPlanIssueCode.COUNT_MISMATCH in result.issue_codes
