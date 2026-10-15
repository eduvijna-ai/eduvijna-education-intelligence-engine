from __future__ import annotations

import re

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticIssueCode

_NONSENSE_MARKERS = (
    "asdf",
    "random",
    "nonsense",
    "???",
    "idk",
    "no idea",
)


def validate_plausibility(tag: OptionDiagnosticTag, option_text: str) -> list[str]:
    if tag.is_correct:
        return []
    text = option_text.strip().lower()
    if not text or len(text) < 1:
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    if any(marker in text for marker in _NONSENSE_MARKERS):
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    if re.fullmatch(r"[^a-z0-9+.\- ]+", text):
        return [DiagnosticIssueCode.NONSENSICAL_DISTRACTOR.value]
    return []
