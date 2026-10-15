from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import DiagnosticQuestionItem, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode


def _extract_addition(stem: str) -> tuple[int, int] | None:
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def validate_factual_incorrectness(
    item: DiagnosticQuestionItem, tag: OptionDiagnosticTag, option_text: str
) -> list[str]:
    if tag.is_correct:
        return []
    pair = _extract_addition(item.stem_text)
    if pair is None:
        return []
    expected = pair[0] + pair[1]
    digits = re.findall(r"\d+", option_text)
    if not digits:
        return []
    for value in digits:
        if int(value) == expected:
            return [DiagnosticIssueCode.SECOND_CORRECT_DISTRACTOR.value]
    return []
