from __future__ import annotations

from typing import Any

from app.learner_intelligence.enums import EligibilityTrustMode


def build_day15_governance_record() -> dict[str, Any]:
    """D15-01: preserve Day11–14 deferrals, containment, and PG0021 blocker."""

    return {
        "day15_scope": "D15-01..D15-36",
        "implementation_branch": "feature/day15-learner-intelligence",
        "tasklist_issue": 56,
        "day11_state": "ON_HOLD",
        "day11_pr": 31,
        "day12_state": "FOUNDER_MILESTONE_SIGNED_OFF_WITH_DEFERRALS",
        "day12_deferred_ledger": "0 PASS / 32 PARTIAL / 3 SOURCE_PENDING / 1 NOT_STARTED",
        "day13_state": "FOUNDER_MILESTONE_SIGNED_OFF_WITH_DEFERRALS",
        "day13_deferred_ledger": "0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED",
        "day14_state": "FOUNDER_MILESTONE_SIGNED_OFF_WITH_DEFERRALS",
        "day14_deferred_ledger": "0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED",
        "day14_containment": "ACADEMIC_VALIDATION_AND_ISSUANCE_DISABLED",
        "day15_state": "ACTIVE",
        "day15_founder_approval": False,
        "day16_state": "LOCKED",
        "postgresql_migration_0021": "BLOCKER_DEFERRED_NOT_PASSED",
        "stopped_workstreams": ["F03-A", "F03-B", "F04-A", "D13-31A"],
        "core_35_official_intake_live": False,
        "production_assessment_eligibility": False,
        "synthetic_harness_required": True,
        "trust_modes": [mode.value for mode in EligibilityTrustMode],
        "evidence_matrix_path": "docs/execution/D15-SCOPE-MAP.md",
        "mastery_policy_path": "docs/execution/D15-MASTERY-POLICY-v1.md",
    }