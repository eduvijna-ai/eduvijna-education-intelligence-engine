"""Canonical numeric token parsing for arithmetic diagnostic validators."""

from __future__ import annotations

import re

_NUMERIC_LITERAL = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])")


def iter_numeric_literals(text: str) -> list[str]:
    return [match.group(0) for match in _NUMERIC_LITERAL.finditer(text)]


def numeric_literal_matches_integer(text: str, expected: int) -> bool:
    """True when a standalone numeric token equals expected (11 and 11.0 ok; 11.9 not)."""
    target = float(expected)
    for token in iter_numeric_literals(text):
        try:
            value = float(token)
        except ValueError:
            continue
        if abs(value - target) > 1e-9:
            continue
        if "." in token.lstrip("-"):
            fractional = token.lstrip("-").split(".", 1)[1]
            if fractional and int(fractional) != 0:
                continue
        return True
    return False


def numeric_literal_equals_correct_sum(option_text: str, correct_sum: int) -> bool:
    return numeric_literal_matches_integer(option_text, correct_sum)
