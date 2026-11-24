from __future__ import annotations

from typing import Any

from app.ca_imat_eapcet.enums import Day14SourceTrustMode


def build_day14_governance_record() -> dict[str, Any]:
    """D14-01: scope freeze preserving Day11–13 deferrals and stopped workstreams."""

    return {
        "day14_scope": "D14-01..D14-36",
        "implementation_branch": "feature/day14-ca-imat-eapcet-intelligence",
        "tasklist_issue": 54,
        "day11_state": "ON_HOLD",
        "day11_pr": 31,
        "day12_state": "FOUNDER_MILESTONE_SIGNED_OFF_WITH_DEFERRALS",
        "day12_deferred_ledger": "0 PASS / 32 PARTIAL / 3 SOURCE_PENDING / 1 NOT_STARTED",
        "day13_state": "FOUNDER_MILESTONE_SIGNED_OFF_WITH_DEFERRALS",
        "day13_deferred_ledger": "0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED",
        "day14_state": "ACTIVE",
        "day14_founder_approval": False,
        "day15_state": "LOCKED",
        "core_35_official_intake_live": False,
        "stopped_workstreams": ["F03-A", "F03-B", "F04-A", "D13-31A"],
        "postgresql_migration_0021": "BLOCKER_DEFERRED_NOT_PASSED",
        "dependency_exception": "FOUNDER_APPROVED_DAY13_MILESTONE_WITH_DEFERRALS",
        "trust_modes": [mode.value for mode in Day14SourceTrustMode],
        "trust_mode_definitions": {
            Day14SourceTrustMode.SYNTHETIC_FIXTURE.value: (
                "Demonstration-only; never curator-approved official evidence."
            ),
            Day14SourceTrustMode.CA_ICAI_REFERENCE.value: (
                "ICAI session syllabus/RTP; SOURCE_PENDING until curator SHA."
            ),
            Day14SourceTrustMode.IMAT_DM1005_2026.value: (
                "MUR D.M.1005 2026/27; official replica requires staged annex bytes."
            ),
            Day14SourceTrustMode.EAPCET_DISCOVERY_MIRROR_ONLY.value: (
                "Aglasem mirror is discovery-only; not activation authority."
            ),
        },
        "evidence_matrix_path": "docs/execution/D14-SCOPE-MAP.md",
        "ca_official_replica_enabled": False,
        "imat_official_replica_enabled": False,
        "eapcet_official_replica_enabled": False,
    }