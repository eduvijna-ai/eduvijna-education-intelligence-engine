"""C01 Gate B shared CHECK text (migrations only — keep model parity by hand)."""

from __future__ import annotations

SOURCE_REVISION_ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)


def d13_synthetic_check_sql(dialect: str) -> str:
    """Exact synthetic-only containment: SQLite integer 1; PostgreSQL boolean true."""
    if dialect == "postgresql":
        return "synthetic_test_only IS TRUE"
    return "synthetic_test_only = 1"


D13_SYNTHETIC_TEST_ONLY_CHECK_SQLITE = "synthetic_test_only = 1"