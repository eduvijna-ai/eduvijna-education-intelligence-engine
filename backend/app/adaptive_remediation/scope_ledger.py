"""D16 scope map row tally and integrity."""

from __future__ import annotations

import re
from pathlib import Path

_ALLOWED = frozenset({"PASS", "PARTIAL", "SOURCE_PENDING", "NOT_STARTED"})
_EXPECTED_IDS = tuple(f"D16-{i:02d}" for i in range(1, 37))


def _normalize_state(raw: str) -> str | None:
    key = raw.strip().upper().replace(" ", "_")
    if key.startswith("NOT_STARTED"):
        return "NOT_STARTED"
    if key in _ALLOWED:
        return key
    return None


def resolve_scope_map_path() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[3] / "docs" / "execution" / "D16-SCOPE-MAP.md",
        here.parents[2] / "docs" / "execution" / "D16-SCOPE-MAP.md",
        Path("/app/docs/execution/D16-SCOPE-MAP.md"),
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def parse_scope_map_counts(markdown: str) -> dict[str, int]:
    rows = re.findall(r"\|\s*D16-\d{2}\s*\|[^|]+\|[^|]+\|\s*(\w+)\s*\|", markdown)
    counts = {state: 0 for state in _ALLOWED}
    for state in rows:
        key = _normalize_state(state)
        if key is not None:
            counts[key] += 1
    counts["TOTAL"] = len(rows)
    return counts


def validate_scope_map_integrity(markdown: str) -> tuple[bool, tuple[str, ...]]:
    found = re.findall(r"\|\s*(D16-\d{2})\s*\|", markdown)
    states = re.findall(r"\|\s*D16-\d{2}\s*\|[^|]+\|[^|]+\|\s*(\w+)\s*\|", markdown)
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
    if len(states) != 36:
        issues.append("ROW_COUNT_NOT_36")
    for raw in states:
        if _normalize_state(raw) is None:
            issues.append(f"INVALID_STATE:{raw.strip()}")
    counts = parse_scope_map_counts(markdown)
    if counts.get("TOTAL") != 36:
        issues.append("ROW_COUNT_NOT_36")
    if sum(counts.get(s, 0) for s in _ALLOWED) != 36:
        issues.append("STATE_SUM_NOT_36")
    return (len(issues) == 0, tuple(issues))


def load_repo_scope_counts(repo_root: Path | None = None) -> dict[str, int]:
    path = (
        repo_root / "docs" / "execution" / "D16-SCOPE-MAP.md"
        if repo_root is not None
        else resolve_scope_map_path()
    )
    return parse_scope_map_counts(path.read_text(encoding="utf-8"))