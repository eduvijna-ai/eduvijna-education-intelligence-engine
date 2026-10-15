from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception

_REPORTED_ANSWER = re.compile(r"reports\s+(\d+)\s+when\s+adding", re.IGNORECASE)


def _extract_addition(stem: str) -> tuple[int, int] | None:
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _reported_wrong_answer(error_pattern: str) -> str | None:
    match = _REPORTED_ANSWER.search(error_pattern)
    if not match:
        return None
    return match.group(1)


def _haystack_contains_wrong_answer(haystack: str, wrong_answer: str) -> bool:
    return bool(re.search(rf"\b{re.escape(wrong_answer)}\b", haystack))


def _text_matches_approved_signal(
    option_text: str,
    stem_text: str,
    definition_signal: str,
    error_pattern: str,
) -> bool:
    haystack = option_text.lower()
    pair = _extract_addition(stem_text)
    reported = _reported_wrong_answer(error_pattern)
    if pair is not None and reported is not None:
        correct_sum = pair[0] + pair[1]
        if int(reported) == correct_sum:
            return False
        return _haystack_contains_wrong_answer(haystack, reported)
    signal = definition_signal.strip().lower()
    if signal and (signal in haystack or signal.replace("-", " ") in haystack):
        return True
    return False


def validate_signal_alignment(
    tag: OptionDiagnosticTag,
    option_text: str,
    *,
    stem_text: str = "",
    taxonomy_version: str | None = None,
) -> list[str]:
    if tag.is_correct or not tag.misconception_code:
        return []
    version = taxonomy_version or tag.taxonomy_version
    definition = resolve_misconception(tag.misconception_code, taxonomy_version=version)
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
