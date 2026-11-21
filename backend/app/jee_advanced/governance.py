from __future__ import annotations

from typing import Any

from app.jee_advanced.enums import JeeAdvancedSourceTrustMode


def build_day12_governance_record() -> dict[str, Any]:
    """D12-01: frozen scope, Day11 hold exception, and trust-mode hierarchy."""

    return {
        "day12_scope": "D12-01..D12-36",
        "implementation_branch": "feature/day12-jee-advanced-intelligence",
        "day11_state": "ON_HOLD",
        "day11_pr": 31,
        "day11_unmerged_rule": "no_cherry_pick_or_silent_dependency",
        "day12_state": "ACTIVE",
        "day12_founder_approval": False,
        "day13_state": "LOCKED",
        "dependency_exception": "FOUNDER_APPROVED_DAY11_ON_HOLD_2026_11_12",
        "trust_modes": [mode.value for mode in JeeAdvancedSourceTrustMode],
        "trust_mode_definitions": {
            JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE.value: (
                "Clearly labelled demonstration content; never authoritative official evidence."
            ),
            JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026.value: (
                "2026 IIT/JAB originals with curator-approved revision; "
                "required for reference replica."
            ),
            JeeAdvancedSourceTrustMode.OFFICIAL_2027_NOT_VERIFIED.value: (
                "2027 pattern fail-closed until distinct approved 2027 brochure/rules exist."
            ),
        },
        "evidence_matrix_path": "docs/execution/D12-SCOPE-MAP.md",
        "implementation_gate_path": "docs/execution/D12-IMPLEMENTATION-GATE.md",
        "tasklist_issue": 33,
    }
