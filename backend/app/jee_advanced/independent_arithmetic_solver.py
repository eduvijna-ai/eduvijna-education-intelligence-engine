"""Test-local arithmetic MCQ solver from display-only stem/options (Issue #50)."""

from __future__ import annotations

import re
from typing import Any


def propose_answer_from_display(display: dict[str, Any]) -> str | None:
    stem = str(display.get("stem_text") or "")
    numbers = [int(m) for m in re.findall(r"\d+", stem)]
    if len(numbers) < 2:
        return None
    total = numbers[0] + numbers[1]
    for raw in list(display.get("options") or []):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if text == str(total):
            key = str(raw.get("option_key") or "").strip()
            if key:
                return key
    return None