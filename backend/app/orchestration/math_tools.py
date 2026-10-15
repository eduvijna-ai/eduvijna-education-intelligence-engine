from __future__ import annotations

import re

from app.orchestration.contracts import DraftQuestionItem, SolverResult


def deterministic_math_check(item: DraftQuestionItem, solver: SolverResult) -> tuple[str, bool]:
    """Return (check_status, blocking_mismatch). Unsupported checks return unknown."""
    stem = item.stem_text.lower()
    match = re.search(r"what is\s+(\d+)\s*\+\s*(\d+)", stem)
    if not match:
        return "unknown", False
    expected = str(int(match.group(1)) + int(match.group(2)))
    correct_keys = [opt.option_key for opt in item.options if opt.is_correct]
    if not correct_keys:
        return "unknown", False
    expected_key = correct_keys[0]
    for opt in item.options:
        if opt.option_key == expected_key and opt.text.strip() == expected:
            if solver.proposed_answer_key == expected_key:
                return "ok", False
            return "mismatch", True
    return "unknown", False
