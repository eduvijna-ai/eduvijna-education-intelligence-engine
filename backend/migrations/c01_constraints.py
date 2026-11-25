"""C01 Gate B shared CHECK text (re-export from app for Alembic)."""

from __future__ import annotations

from app.db.c01_portable_checks import (  # noqa: F401
    D13_SYNTHETIC_TEST_ONLY_CHECK,
    SOURCE_REVISION_ACTIVE_SLOT_CHECK,
)


def d13_synthetic_check_sql(dialect: str) -> str:
    """Portable exact containment (dialect-agnostic SQL text)."""
    del dialect
    return D13_SYNTHETIC_TEST_ONLY_CHECK