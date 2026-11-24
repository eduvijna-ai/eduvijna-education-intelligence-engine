"""D16 scope map row tally and integrity."""

from __future__ import annotations

import re
from pathlib import Path

_ALLOWED = frozenset({"PASS", "PARTIAL", "SOURCE_PENDING", "NOT_STARTED"})
_EXPECTED_IDS = tuple(f"D16-{i:02d}" for i in range(1, 37))


def parse_scope_map_counts(markdown: str) -> dict[str, int]:
    rows = re.findall(r"\|\s*D16-\d{2}\s*\|[^|]+\|[^|]+\|\s*(\w+)\s*\|", markdown)
    counts = {state: 0 for state in _ALLOWED}
    for state in rows:
        key = state.strip().upper().replace(" ", "_")
        if key.startswith("NOT_STARTED"):
            key = "NOT_STARTED"
        if key in counts:
            counts[key] += 1
    counts["TOTAL"] = len(rows)
    return counts


def validate_scope_map_integrity(markdown: str) -> tuple[bool, tuple[str, ...]]:
    found = re.findall(r"\|\s*(D16-\d{2})\s*\|", markdown)
    issues: list[str] = []
    if len(found) != len(set(found)):
        issues.append("DUPLICATE_D16_ROWS")
    if set(found) != set(_EXPECTED_IDS):
        missing = sorted(set(_EXPECTED_IDS) - set(found))
        extra = sorted(set(found) - set(_EXPECTED_IDS))
        if missing:
            issues.append(f"MISSING_IDS:{','.join(missing)}")
        if extra:
            issues.append(f"EXTRA_IDS:{','.join(extra)}")
    counts = parse_scope_map_counts(markdown)
    if counts.get("TOTAL") != 36:
        issues.append("ROW_COUNT_NOT_36")
    for state in _ALLOWED:
        if state not in counts:
            issues.append(f"MISSING_STATE_{state}")
    return (len(issues) == 0, tuple(issues))


def load_repo_scope_counts(repo_root: Path | None = None) -> dict[str, int]:
    root = Path(__file__).resolve().parents[3]
    if repo_root is not None:
        root = repo_root
    elif not (root / "docs" / "execution" / "D16-SCOPE-MAP.md").exists():
        root = Path(__file__).resolve().parents[2]
    path = root / "docs" / "execution" / "D16-SCOPE-MAP.md"
    return parse_scope_map_counts(path.read_text(encoding="utf-8"))
