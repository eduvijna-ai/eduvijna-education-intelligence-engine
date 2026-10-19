"""Canonical numeric token parsing for arithmetic diagnostic validators."""

from __future__ import annotations

import re

# Standalone numeric literals only; reject fraction/scientific tails (11/9, 11e2).
_NUMERIC_LITERAL = re.compile(r"(?<![\d./eE])-?(\d+)(?:\.(\d+))?(?![\d.eE/])")
_UNSUPPORTED_EXPRESSION = re.compile(
    r"\d\s*[/^%*×÷:]\s*\d"
    r"|\d\s*[eE]\s*[+\-]?\s*\d"
    r"|\d\s*\+\s*\d"
    r"|\d\s*-\s*\d"
    r"|\d\s*[xX]\s*\d"
    r"|\d\s+times\s+\d"
    r"|\(\s*\d"
)
_SIMPLE_ADDITION = re.compile(r"^\s*(\d+)\s*\+\s*(\d+)\s*$")


def has_unsupported_arithmetic_expression(text: str) -> bool:
    """True when text looks like an arithmetic expression, not a standalone literal."""
    return bool(_UNSUPPORTED_EXPRESSION.search(text.strip()))


def iter_numeric_literals(text: str) -> list[str]:
    if has_unsupported_arithmetic_expression(text):
        return []
    tokens: list[str] = []
    for match in _NUMERIC_LITERAL.finditer(text):
        fractional = match.group(2)
        if fractional is not None and fractional != "" and int(fractional) != 0:
            continue
        tokens.append(match.group(0))
    return tokens


def numeric_literal_matches_integer(text: str, expected: int) -> bool:
    """True when a standalone numeric token equals expected (11 and 11.0 ok; 11.9 not)."""
    if has_unsupported_arithmetic_expression(text):
        return False
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
    stripped = option_text.strip()
    if has_unsupported_arithmetic_expression(stripped):
        match = _SIMPLE_ADDITION.match(stripped)
        if match is not None:
            return int(match.group(1)) + int(match.group(2)) == correct_sum
        return False
    return numeric_literal_matches_integer(option_text, correct_sum)
