"""Canonical numeric token parsing for arithmetic diagnostic validators."""

from __future__ import annotations

import re

# Standalone numeric literals only; reject fraction/scientific tails (11/9, 11e2).
_NUMERIC_LITERAL = re.compile(r"(?<![\d./eE])-?(\d+)(?:\.(\d+))?(?![\d.eE/])")


def iter_numeric_literals(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _NUMERIC_LITERAL.finditer(text):
        fractional = match.group(2)
        if fractional is not None and fractional != "" and int(fractional) != 0:
            continue
        tokens.append(match.group(0))
    return tokens


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
        return True
    return False


def numeric_literal_equals_correct_sum(option_text: str, correct_sum: int) -> bool:
    return numeric_literal_matches_integer(option_text, correct_sum)
