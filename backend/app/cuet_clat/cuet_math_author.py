"""Synthetic CUET Mathematics item specifications (original, deterministic, D13-F03-A)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CuetMathAuthoredItem:
    """Author output before persistence — solver must verify independently."""

    external_code: str
    stem_text: str
    topic_code: str
    option_text_by_key: dict[str, str]
    author_selected_key: str
    solution_steps: tuple[str, ...]


OPTION_KEYS = ("A", "B", "C", "D")


def _distinct_distractors(correct: int, index: int) -> list[int]:
    candidates = [correct + 1, correct - 1, correct + 2, correct + 3, correct - 2, correct + 5]
    out: list[int] = []
    for value in candidates:
        if value == correct or value in out or value < 0:
            continue
        out.append(value)
        if len(out) == 3:
            break
    while len(out) < 3:
        filler = correct + 10 + index + len(out)
        if filler != correct and filler not in out:
            out.append(filler)
    return out


def generate_cuet_math_authored_items(*, count: int = 50) -> list[CuetMathAuthoredItem]:
    """Build up to `count` distinct addition MCQs with rotating correct keys."""

    if count <= 0:
        return []
    items: list[CuetMathAuthoredItem] = []
    for index in range(count):
        a = 11 + index
        b = 17 + (index % 13)
        correct_value = a + b
        distractors = _distinct_distractors(correct_value, index)
        correct_key = OPTION_KEYS[index % len(OPTION_KEYS)]
        distractor_keys = [k for k in OPTION_KEYS if k != correct_key]
        text_by_key: dict[str, str] = {}
        text_by_key[correct_key] = str(correct_value)
        for key, wrong in zip(distractor_keys, distractors, strict=True):
            text_by_key[key] = str(wrong)
        stem = f"Synthetic CUET Mathematics: what is {a} + {b}?"
        items.append(
            CuetMathAuthoredItem(
                external_code=f"d13-cuet-math-{index:03d}",
                stem_text=stem,
                topic_code="algebra_basics" if index % 2 == 0 else "arithmetic_basics",
                option_text_by_key=text_by_key,
                author_selected_key=correct_key,
                solution_steps=(f"Compute {a} + {b}", f"Sum equals {correct_value}"),
            )
        )
    return items