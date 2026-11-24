from __future__ import annotations

from typing import Any

from app.cuet_clat.enums import CuetClatSourceTrustMode


def build_day13_governance_record() -> dict[str, Any]:
    """D13-01: scope freeze, Day11 hold, Day12 deferrals, trust-mode hierarchy."""

    return {
        "day13_scope": "D13-01..D13-36",
        "implementation_branch": "feature/day13-cuet-clat-intelligence",
        "tasklist_issue": 52,
        "day11_state": "ON_HOLD",
        "day11_pr": 31,
        "day11_unmerged_rule": "no_cherry_pick_or_silent_dependency",
        "day12_state": "FOUNDER_SIGNOFF_WITH_DEFERRALS",
        "day12_pr": 34,
        "day13_state": "ACTIVE",
        "day13_founder_approval": False,
        "day14_state": "LOCKED",
        "core_35_official_intake_live": False,
        "dependency_exception": "FOUNDER_APPROVED_DAY11_ON_HOLD_2026_11_23",
        "trust_modes": [mode.value for mode in CuetClatSourceTrustMode],
        "trust_mode_definitions": {
            CuetClatSourceTrustMode.SYNTHETIC_FIXTURE.value: (
                "Demonstration-only; never curator-approved official evidence."
            ),
            CuetClatSourceTrustMode.CUET_HISTORICAL_2026.value: (
                "CUET UG 2026 NTA bulletin/syllabus; SOURCE_PENDING until curator SHA."
            ),
            CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED.value: (
                "CUET 2027 fail-closed until distinct approved official release."
            ),
            CuetClatSourceTrustMode.CLAT_OFFICIAL_2027.value: (
                "CLAT UG 2027 Consortium format/syllabus; official replica requires staging."
            ),
        },
        "evidence_matrix_path": "docs/execution/D13-SCOPE-MAP.md",
        "cuet_official_replica_enabled": False,
        "clat_official_replica_enabled": False,
    }