"""C01 Gate B shared CHECK text (migrations only — keep model parity by hand)."""

from __future__ import annotations

SOURCE_REVISION_ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)

D13_SYNTHETIC_TEST_ONLY_CHECK = "synthetic_test_only IS TRUE"