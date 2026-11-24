from __future__ import annotations

import re
from pathlib import Path

_ALLOWED = frozenset({"PASS", "PARTIAL", "SOURCE_PENDING", "NOT_STARTED"})


def parse_scope_map_counts(markdown: str) -> dict[str, int]:
    rows = re.findall(r"\|\s*D15-\d{2}\s*\|[^|]+\|[^|]+\|\s*(\w+)\s*\|", markdown)
    counts = {state: 0 for state in _ALLOWED}
    for state in rows:
        key = state.strip().upper().replace(" ", "_")
        if key.startswith("NOT_STARTED"):
            key = "NOT_STARTED"
        if key.startswith("SOURCE"):
            key = "SOURCE_PENDING"
        if key in counts:
            counts[key] += 1
    counts["TOTAL"] = len(rows)
    return counts


def load_repo_scope_counts(repo_root: Path | None = None) -> dict[str, int]:
    root = Path(__file__).resolve().parents[3]
    if repo_root is not None:
        root = repo_root
    elif not (root / "docs" / "execution" / "D15-SCOPE-MAP.md").exists():
        root = Path(__file__).resolve().parents[2]
    path = root / "docs" / "execution" / "D15-SCOPE-MAP.md"
    return parse_scope_map_counts(path.read_text(encoding="utf-8"))