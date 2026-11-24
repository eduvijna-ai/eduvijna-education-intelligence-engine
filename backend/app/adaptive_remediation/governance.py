"""D16-01 governance record."""

from __future__ import annotations

from typing import Any

from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED


def build_day16_governance_record() -> dict[str, Any]:
    return {
        "day16_scope": "D16-01..D16-36",
        "implementation_branch": "feature/day16-adaptive-remediation",
        "tasklist_issue": 58,
        "planning_base_sha": "f8e96ceecbe42cdbcc1cca9de3dd13852a648ec4",
        "day15_state": "ON_HOLD",
        "day15_pr": 57,
        "day15_import_forbidden": True,
        "day17_state": "LOCKED",
        "dependency_exception": "FOUNDER_APPROVED_DAY15_ON_HOLD_2026_11_24",
        "dependency_strategy": "DEVELOP_BASE_NO_UNMERGED_D15",
        "runtime_learner_remediation": "DISABLED",
        "diagnostic_scope": "PURE_SYNTHETIC_NON_ACTIONABLE_ONLY",
        "day14_containment_preserved": {
            "academic_validation_disabled": ACADEMIC_VALIDATION_DISABLED,
            "issuance_disabled": ISSUANCE_DISABLED,
        },
        "day11_state": "ON_HOLD",
        "day12_deferred_ledger": "0 PASS / 32 PARTIAL / 3 SOURCE_PENDING / 1 NOT_STARTED",
        "day13_deferred_ledger": "0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED",
        "day14_deferred_ledger": "0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED",
        "day15_deferred_ledger": "0 PASS / 35 PARTIAL / 1 NOT_STARTED",
        "evidence_matrix_path": "docs/execution/D16-SCOPE-MAP.md",
        "founder_approval": False,
        "auto_merge": False,
    }
