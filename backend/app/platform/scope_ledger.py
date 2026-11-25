from __future__ import annotations

import re
from pathlib import Path

_VALID_STATUSES = frozenset({"PASS", "PARTIAL", "BLOCKED", "NOT_STARTED", "SOURCE_PENDING"})


def resolve_scope_map_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "docs" / "execution" / "D17-SCOPE-MAP.md"


def load_scope_rows(markdown: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in markdown.splitlines():
        if not line.startswith("| D17-"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        task_id = parts[1]
        status = parts[4]
        if not re.fullmatch(r"D17-\d{2}", task_id):
            continue
        if status not in _VALID_STATUSES:
            continue
        rows.append((task_id, status))
    return rows


def validate_scope_map(markdown: str) -> tuple[bool, dict[str, int], list[str]]:
    rows = load_scope_rows(markdown)
    issues: list[str] = []
    ids = [task_id for task_id, _ in rows]
    if len(ids) != len(set(ids)):
        issues.append("duplicate D17 task ids")
    if len(ids) != 36:
        issues.append(f"expected 36 rows, found {len(ids)}")
    expected = {f"D17-{i:02d}" for i in range(1, 37)}
    missing = sorted(expected - set(ids))
    if missing:
        issues.append(f"missing ids: {missing[0]}")
    counts = {status: 0 for status in _VALID_STATUSES}
    for _, status in rows:
        counts[status] += 1
    counts["TOTAL"] = len(rows)
    return not issues, counts, issues