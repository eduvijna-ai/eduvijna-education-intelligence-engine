from __future__ import annotations

import re

_SUFFIX_RE = re.compile(r"\s*\((?:item\s+)?\d+\)\s*$")
_SCENARIO_RE = re.compile(r"\s+Scenario\s+\d+\.\s*$")


def semantic_stem_key(stem: str) -> str:
    """Normalize stems so index-only suffix clones count as duplicates."""

    base = stem.strip()
    base = _SUFFIX_RE.sub("", base)
    base = _SCENARIO_RE.sub("", base)
    return base.lower()