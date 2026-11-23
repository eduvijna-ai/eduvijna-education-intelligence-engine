"""Independent CUET math solver — does not trust author answer keys (D13-F03-A)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.cuet_clat.cuet_math_author import CuetMathAuthoredItem
from app.models import Question

_ADD_PATTERN = re.compile(
    r"Synthetic CUET Mathematics: what is (\d+) \+ (\d+)\?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CuetSolverEvidence:
    evidence_id: str
    answer_key: str
    computed_value: int
    steps: tuple[str, ...]


def solve_authored_item(item: CuetMathAuthoredItem) -> CuetSolverEvidence | None:
    match = _ADD_PATTERN.match(item.stem_text.strip())
    if not match:
        return None
    left = int(match.group(1))
    right = int(match.group(2))
    total = left + right
    derived_key: str | None = None
    for key, text in item.option_text_by_key.items():
        if text.strip() == str(total):
            derived_key = key
            break
    if derived_key is None:
        return None
    steps = (
        f"Parse stem operands {left} and {right}",
        f"Compute sum {left} + {right} = {total}",
        f"Select option key whose text equals {total}",
    )
    return CuetSolverEvidence(
        evidence_id=f"d13-solver-{item.external_code}",
        answer_key=derived_key,
        computed_value=total,
        steps=steps,
    )


def solver_confirms_author(item: CuetMathAuthoredItem) -> tuple[bool, CuetSolverEvidence | None]:
    evidence = solve_authored_item(item)
    if evidence is None:
        return False, None
    return evidence.answer_key == item.author_selected_key, evidence


def solve_persisted_question(question: Question) -> CuetSolverEvidence | None:
    """Re-derive answer from visible stem/options only (no answer_json trust)."""

    match = _ADD_PATTERN.match((question.stem_text or "").strip())
    if not match:
        return None
    left = int(match.group(1))
    right = int(match.group(2))
    total = left + right
    derived_key: str | None = None
    matches = 0
    for opt in question.options:
        if opt.text.strip() == str(total):
            derived_key = opt.option_key
            matches += 1
    if derived_key is None or matches != 1:
        return None
    code = (question.external_code or str(question.id)).strip()
    steps = (
        f"Parse stem operands {left} and {right}",
        f"Compute sum {left} + {right} = {total}",
        f"Select option key whose text equals {total}",
    )
    return CuetSolverEvidence(
        evidence_id=f"d13-solver-{code}",
        answer_key=derived_key,
        computed_value=total,
        steps=steps,
    )