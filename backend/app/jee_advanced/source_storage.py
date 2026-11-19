"""Resolve Day3 source byte storage for authority checks (production path)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.source_intelligence.storage import LocalSourceStorage

_SYNTHETIC_META_KEYS = (
    "d12_core_test_fixture",
    "synthetic_nta_harness",
    "synthetic_test",
)


def official_source_storage() -> LocalSourceStorage | None:
    """Configured private source directory; None when unavailable."""

    try:
        root = Path(get_settings().source_storage_dir).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return LocalSourceStorage(root)
    except OSError:
        return None


def metadata_marks_synthetic(meta: dict[str, object]) -> bool:
    for key in _SYNTHETIC_META_KEYS:
        if meta.get(key):
            return True
    return False