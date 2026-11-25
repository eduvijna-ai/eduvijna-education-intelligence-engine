"""D17-01 governance record."""

from __future__ import annotations

from typing import Any


def build_day17_governance_record() -> dict[str, Any]:
    return {
        "day17_scope": "D17-01..D17-36",
        "implementation_branch": "feature/day17-rest-jobs-auth-mcp",
        "tasklist_issue": 60,
        "planning_base_sha": "9400ce13af13c13c5158fa06c90f7f2517abbe93",
        "day11_state": "ON_HOLD",
        "day12_live_source_intake": "DISABLED",
        "day13_pg0021": "BLOCKER_DEFERRED",
        "day14_containment": "ACADEMIC_VALIDATION_AND_ISSUANCE_DISABLED",
        "day15_state": "ON_HOLD",
        "day15_pr": 57,
        "day16_runtime_remediation": "DISABLED",
        "day18_state": "LOCKED",
        "dependency_exception": "FOUNDER_APPROVED_DAY16_MILESTONE_WITH_DEFERRALS",
        "dependency_strategy": "DEVELOP_BASE_NO_UNMERGED_D11_D15",
        "founder_approval": False,
        "auto_merge": False,
        "implementation_candidate": 3,
        "implementation_candidate_limit": 3,
    }
