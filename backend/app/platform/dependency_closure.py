"""D17-01 dependency closure register."""

from __future__ import annotations

from typing import Any


def build_day17_dependency_closure_register() -> dict[str, Any]:
    return {
        "day4_official_source_issue": 12,
        "day5_source_deferred_issue": 16,
        "day11_jee_main": {"state": "ON_HOLD", "pr": 31, "import_forbidden": True},
        "day12_jee_advanced": {
            "state": "MERGED_DEFERRED",
            "source_live_intake": "DISABLED",
            "issue": 35,
        },
        "day13_cuet_clat": {"state": "MERGED_DEFERRED", "pg_migration_0021": "BLOCKER"},
        "day14_ca_imat_eapcet": {
            "state": "MERGED_DEFERRED",
            "academic_validation": "DISABLED",
            "issuance": "DISABLED",
        },
        "day15_learner_intelligence": {"state": "ON_HOLD", "pr": 57, "import_forbidden": True},
        "day16_adaptive_remediation": {
            "state": "MERGED_DEFERRED",
            "runtime_remediation": "DISABLED",
        },
        "day17_rest_auth_mcp": {"state": "ACTIVE"},
        "day18_react_surfaces": {"state": "LOCKED"},
        "held_import_policy": "NO_CHERRY_PICK_FROM_HOLD_PRS",
    }
