from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.validators.signal import (
    arithmetic_operands_from_stem,
    expected_wrong_answer_for_code,
)

_NONSENSE_MARKERS = (
    "asdf",
    "random",
    "nonsense",
    "???",
    "idk",
    "no idea",
)


def validate_plausibility(
    tag: OptionDiagnosticTag,
    option_text: str,
    *,
    stem_text: str = "",
    taxonomy_version: str | None = None,
) -> list[str]:
    if tag.is_correct:
        return []
    text = option_text.strip().lower()
    if not text or len(text) < 1:
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    if any(marker in text for marker in _NONSENSE_MARKERS):
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    if re.fullmatch(r"[^a-z0-9+.\- ]+", text):
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    if tag.misconception_code and stem_text and taxonomy_version:
        operands = arithmetic_operands_from_stem(stem_text)
        if operands is not None:
            expected = expected_wrong_answer_for_code(
                tag.misconception_code, operands, taxonomy_version=taxonomy_version
            )
            if expected is not None and re.search(
                rf"\b{re.escape(str(expected))}\b", option_text
            ):
                return []
            for code in (
                "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "MATH.ADD.WHOLE.SUM_AS_NEXT",
                "MATH.ADD.WHOLE.DOUBLE_OPERAND",
            ):
                alt = expected_wrong_answer_for_code(
                    code, operands, taxonomy_version=taxonomy_version
                )
                if alt is not None and re.search(
                    rf"\b{re.escape(str(alt))}\b", option_text
                ):
                    return []
            if expected is None:
                return [DiagnosticIssueCode.PLAUSIBILITY_UNVERIFIED.value]
            return [DiagnosticIssueCode.PLAUSIBILITY_UNVERIFIED.value]
    if tag.misconception_code and stem_text:
        return [DiagnosticIssueCode.PLAUSIBILITY_UNVERIFIED.value]
    return []
