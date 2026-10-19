from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import DiagnosticQuestionItem, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.numeric_tokens import numeric_literal_equals_correct_sum
from app.orchestration.contracts import SolverResult


def _extract_addition(stem: str) -> tuple[int, int] | None:
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def validate_factual_incorrectness(
    item: DiagnosticQuestionItem,
    tag: OptionDiagnosticTag,
    option_text: str,
    *,
    solver: SolverResult | None = None,
) -> list[str]:
    if tag.is_correct:
        return []
    pair = _extract_addition(item.stem_text)
    if pair is not None:
        expected = pair[0] + pair[1]
        if numeric_literal_equals_correct_sum(option_text, expected):
            return [DiagnosticIssueCode.SECOND_CORRECT_DISTRACTOR.value]
        return []

    if solver is not None and solver.proposed_answer_key == tag.option_key:
        if solver.agrees_with_author is False or solver.check_status in {
            "mismatch",
            "second_correct",
        }:
            return [DiagnosticIssueCode.SECOND_CORRECT_DISTRACTOR.value]

    return [DiagnosticIssueCode.FACTUAL_UNVERIFIED.value]
