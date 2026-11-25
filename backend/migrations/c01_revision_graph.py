"""Exact C01 Alembic revision graph (21 revisions, ordered)."""

from __future__ import annotations

C01_ALEMBIC_REVISION_GRAPH: tuple[str, ...] = (
    "20261001_0001",
    "20261001_0002",
    "20261001_0003",
    "20261002_0004",
    "20261002_0005",
    "20261003_0006",
    "20261003_0007",
    "20261004_0008",
    "20261004_0009",
    "20261007_0010",
    "20261012_0011",
    "20261015_0012",
    "20261015_0013",
    "20261015_0014",
    "20261102_0015",
    "20261103_0016",
    "20261103_0017",
    "20261109_0018",
    "20261124_0019",
    "20261124_0020",
    "20261124_0021",
)

REV_0021 = "20261124_0021"


def revision_index(revision: str) -> int | None:
    try:
        return C01_ALEMBIC_REVISION_GRAPH.index(revision)
    except ValueError:
        return None


def is_at_or_past_revision(current: str, target: str) -> bool:
    cur_idx = revision_index(current)
    tgt_idx = revision_index(target)
    if cur_idx is None or tgt_idx is None:
        return False
    return cur_idx >= tgt_idx