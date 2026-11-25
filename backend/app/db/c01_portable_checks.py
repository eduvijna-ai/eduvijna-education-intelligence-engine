"""C01 portable CHECK text shared by migrations and ORM metadata."""

from __future__ import annotations

SOURCE_REVISION_ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)

# Exact synthetic containment on both dialects (boolean cast to integer).
D13_SYNTHETIC_TEST_ONLY_CHECK = "CAST(synthetic_test_only AS INTEGER) = 1"