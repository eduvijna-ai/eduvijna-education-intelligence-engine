from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def validate_signal_alignment(
    tag: OptionDiagnosticTag, option_text: str
) -> list[str]:
    if tag.is_correct or not tag.misconception_code:
        return []
    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=tag.taxonomy_version
    )
    if definition is None:
        return [DiagnosticIssueCode.UNKNOWN_MISCONCEPTION_CODE.value]
    signal = (tag.diagnostic_signal or definition.diagnostic_signal).strip().lower()
    if not signal:
        return [DiagnosticIssueCode.SIGNAL_TEXT_MISMATCH.value]
    haystack = option_text.lower()
    if signal not in haystack and signal.replace("-", " ") not in haystack:
        digits = re.findall(r"\d+", definition.error_pattern)
        if not any(digit in haystack for digit in digits):
            return [DiagnosticIssueCode.SIGNAL_TEXT_MISMATCH.value]
    return []
