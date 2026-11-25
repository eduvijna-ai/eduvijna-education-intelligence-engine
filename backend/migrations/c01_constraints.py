"""C01 shared CHECK text (re-export from app for Alembic)."""

from __future__ import annotations

from app.db.c01_portable_checks import SOURCE_REVISION_ACTIVE_SLOT_CHECK
from app.db.c01_portable_checks import d13_synthetic_check_sql as d13_synthetic_check_sql

__all__ = [
    "SOURCE_REVISION_ACTIVE_SLOT_CHECK",
    "d13_synthetic_check_sql",
]