from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.cuet_clat.constants import (
    CLAT_MARK_CORRECT,
    CLAT_MARK_INCORRECT,
    CUET_MARK_CORRECT,
    CUET_MARK_INCORRECT,
    MATHEMATICS_DOMAIN,
)
from app.cuet_clat.contracts import PracticeQuestionRef


@dataclass(frozen=True, slots=True)
class SyntheticFixturePool:
    cuet_math_items: tuple[PracticeQuestionRef, ...]
    pool_fingerprint: str
    demonstration_only: bool = True


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def build_cuet_math_pool(*, size: int = 50) -> SyntheticFixturePool:
    items: list[PracticeQuestionRef] = []
    for i in range(size):
        qid = f"cuet_math_syn_{i:03d}"
        items.append(
            PracticeQuestionRef(
                question_id=qid,
                subject_code=MATHEMATICS_DOMAIN,
                topic_code="algebra_basics",
                fingerprint=_fingerprint("cuet", qid),
                correct_key="A",
                marks_if_correct=CUET_MARK_CORRECT,
                marks_if_incorrect=CUET_MARK_INCORRECT,
            )
        )
    fp = _fingerprint("pool", str(len(items)), items[0].question_id, items[-1].question_id)
    return SyntheticFixturePool(cuet_math_items=tuple(items), pool_fingerprint=fp)


def build_clat_question(
    *,
    section_code: str,
    index: int,
    passage_id: str | None,
) -> PracticeQuestionRef:
    qid = f"clat_{section_code}_{index:03d}"
    return PracticeQuestionRef(
        question_id=qid,
        subject_code=section_code,
        passage_id=passage_id,
        fingerprint=_fingerprint("clat", section_code, qid),
        correct_key="B",
        marks_if_correct=CLAT_MARK_CORRECT,
        marks_if_incorrect=CLAT_MARK_INCORRECT,
    )