from __future__ import annotations

import re
from collections.abc import Callable

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode
from app.diagnostic_intelligence.numeric_tokens import numeric_literal_matches_integer
from app.diagnostic_intelligence.taxonomy_registry import resolve_misconception

_WHOLE_ADD_PATTERN = re.compile(
    r"reports\s+(\d+)\s+when\s+adding\s+(\d+)\s+and\s+(\d+)",
    re.IGNORECASE,
)

_ARITHMETIC_EXPECTED_WRONG: dict[str, Callable[[int, int], int]] = {
    "MATH.ADD.WHOLE.OFF_BY_ONE_LOW": lambda left, right: left + right - 1,
    "MATH.ADD.WHOLE.SUM_AS_NEXT": lambda left, right: left + right + 1,
    "MATH.ADD.WHOLE.DOUBLE_OPERAND": lambda left, right: left,
}


def _extract_addition(stem: str) -> tuple[int, int] | None:
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem.lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _haystack_contains_wrong_answer(haystack: str, wrong_answer: str) -> bool:
    try:
        expected = int(wrong_answer)
    except ValueError:
        return bool(re.search(rf"\b{re.escape(wrong_answer)}\b", haystack))
    return numeric_literal_matches_integer(haystack, expected)


def _operands_match_pattern(
    stem_left: int, stem_right: int, pattern_left: int, pattern_right: int
) -> bool:
    return (stem_left, stem_right) == (pattern_left, pattern_right)


def _text_matches_approved_signal(
    option_text: str,
    stem_text: str,
    misconception_code: str,
    definition_signal: str,
    error_pattern: str,
) -> bool:
    haystack = option_text.lower()
    pair = _extract_addition(stem_text)
    if pair is None:
        return False
    left, right = pair
    rule = _ARITHMETIC_EXPECTED_WRONG.get(misconception_code)
    if rule is not None:
        expected = rule(left, right)
        return _haystack_contains_wrong_answer(haystack, str(expected))
    pattern = _WHOLE_ADD_PATTERN.search(error_pattern)
    if pattern is None:
        return False
    pattern_wrong = int(pattern.group(1))
    pattern_left = int(pattern.group(2))
    pattern_right = int(pattern.group(3))
    if not _operands_match_pattern(left, right, pattern_left, pattern_right):
        return False
    correct_sum = left + right
    if pattern_wrong == correct_sum:
        return False
    return _haystack_contains_wrong_answer(haystack, str(pattern_wrong))


def arithmetic_operands_from_stem(stem_text: str) -> tuple[int, int] | None:
    return _extract_addition(stem_text)


def expected_wrong_answer_for_code(
    misconception_code: str,
    operands: tuple[int, int],
    *,
    taxonomy_version: str,
) -> int | None:
    left, right = operands
    rule = _ARITHMETIC_EXPECTED_WRONG.get(misconception_code)
    if rule is not None:
        return rule(left, right)
    definition = resolve_misconception(misconception_code, taxonomy_version=taxonomy_version)
    if definition is None:
        return None
    pattern = _WHOLE_ADD_PATTERN.search(definition.error_pattern)
    if pattern is None:
        return None
    pattern_wrong = int(pattern.group(1))
    pattern_left = int(pattern.group(2))
    pattern_right = int(pattern.group(3))
    if not _operands_match_pattern(left, right, pattern_left, pattern_right):
        return None
    return pattern_wrong


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
        tag.misconception_code,
        definition.diagnostic_signal,
        definition.error_pattern,
    ):
        return [DiagnosticIssueCode.SIGNAL_TEXT_MISMATCH.value]
    return []
