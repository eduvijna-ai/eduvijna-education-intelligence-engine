from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception


def _extract_addition(stem: str) -> tuple[int, int] | None:
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _text_matches_approved_signal(
    option_text: str,
    stem_text: str,
    definition_signal: str,
    error_pattern: str,
) -> bool:
    haystack = option_text.lower()
    signal = definition_signal.strip().lower()
    if signal and (signal in haystack or signal.replace("-", " ") in haystack):
        return True
    pair = _extract_addition(stem_text)
    if pair is None:
        return False
    correct_sum = pair[0] + pair[1]
    digits = [int(value) for value in re.findall(r"\d+", error_pattern)]
    wrong_digits = [str(value) for value in digits if value != correct_sum]
    return any(digit in haystack for digit in wrong_digits)


def validate_signal_alignment(
    tag: OptionDiagnosticTag, option_text: str, *, stem_text: str = ""
) -> list[str]:
    if tag.is_correct or not tag.misconception_code:
        return []
    definition = resolve_misconception(
        tag.misconception_code, taxonomy_version=tag.taxonomy_version
    )
    if definition is None:
        return [DiagnosticIssueCode.UNKNOWN_MISCONCEPTION_CODE.value]
    if not _text_matches_approved_signal(
        option_text,
        stem_text,
        definition.diagnostic_signal,
        definition.error_pattern,
    ):
        return [DiagnosticIssueCode.SIGNAL_TEXT_MISMATCH.value]
    return []
