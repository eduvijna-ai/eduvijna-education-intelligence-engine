"""Day 16 verification harness (D16-34)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.adaptive_remediation.containment import (
    CONTAINMENT_MILESTONE,
    PRODUCTION_REMEDIATION_DISABLED,
    SYNTHETIC_DIAGNOSTIC_ONLY,
)
from app.adaptive_remediation.dependency_closure import build_dependency_closure_register
from app.adaptive_remediation.fingerprint import plan_fingerprint
from app.adaptive_remediation.governance import build_day16_governance_record
from app.adaptive_remediation.integration_contracts import build_integration_bridge_status
from app.adaptive_remediation.practice_plan import allocate_stage_counts, count_conservation_ok
from app.adaptive_remediation.prerequisite_plan import graph_ready
from app.adaptive_remediation.production_gate import explain_containment
from app.adaptive_remediation.scope_ledger import load_repo_scope_counts
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def build_verification_report(*, revision: RevisionEvidence) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    scope_counts = load_repo_scope_counts()
    service = AdaptiveRemediationDiagnosticService()
    demo_request = service.build_authoritative_demo_request()
    demo = service.plan(demo_request)
    replay_fp = plan_fingerprint(demo_request, policy_version=demo.policy_version)

    graph = build_friction_remediation_graph()
    g_ok, _, _ = graph_ready(graph)

    counts_ok = {n: allocate_stage_counts(n) is not None for n in (5, 10, 15)}
    conservation = (
        count_conservation_ok(demo.stages, demo.requested_count) if demo.stages else False
    )

    stages_have_all_three = len(demo.stages) >= 3 and {s.stage.value for s in demo.stages} >= {
        "foundation",
        "application",
        "target_retest",
    }

    production_blocked = (
        PRODUCTION_REMEDIATION_DISABLED
        and not demo.production_gate.actionable
        and demo.production_gate.delivered_question_count == 0
        and demo.production_gate.validated_question_count == 0
        and demo.production_gate.scheduled_event_count == 0
    )

    day14_containment_unchanged = ACADEMIC_VALIDATION_DISABLED and ISSUANCE_DISABLED

    diagnostic_execution_ok = (
        revision.sha_aligned
        and scope_counts.get("TOTAL") == 36
        and g_ok
        and all(counts_ok.values())
        and conservation
        and stages_have_all_three
        and production_blocked
        and SYNTHETIC_DIAGNOSTIC_ONLY
        and day14_containment_unchanged
        and demo.verdict.value in {"DIAGNOSTIC_PLAN", "REVIEW_REQUIRED"}
    )

    report: dict[str, object] = {
        "ok": diagnostic_execution_ok,
        "governance": build_day16_governance_record(),
        "containment_milestone": CONTAINMENT_MILESTONE,
        "containment": explain_containment(),
        "production_remediation_disabled": PRODUCTION_REMEDIATION_DISABLED,
        "synthetic_diagnostic_only": SYNTHETIC_DIAGNOSTIC_ONLY,
        "real_academic_readiness": False,
        "actionable_remediation": False,
        "delivered_count": 0,
        "validated_count": 0,
        "synthetic_friction_demo": {
            "verdict": demo.verdict.value,
            "planned_count": demo.planned_count,
            "selected_count": demo.selected_count,
            "stages": [s.stage.value for s in demo.stages],
            "fingerprint": demo.fingerprint,
        },
        "count_conservation_ok": conservation,
        "exact_count_checks": counts_ok,
        "integration_bridge": asdict(build_integration_bridge_status()),
        "dependency_closure": build_dependency_closure_register(),
        "scope_ledger_counts": scope_counts,
        "day14_academic_validation_disabled": ACADEMIC_VALIDATION_DISABLED,
        "day14_issuance_disabled": ISSUANCE_DISABLED,
        "fingerprint_replay_self_consistent": demo.fingerprint == replay_fp,
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "anythingllm_live": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "d16_36_founder_signoff": "NOT_STARTED",
            "migration_0022_day15": "HELD_NOT_IMPORTED",
        },
    }
    report.update(revision.as_report_fields())
    return report


def _revision_failure_report(revision: RevisionEvidence) -> dict[str, object]:
    try:
        scope_counts = load_repo_scope_counts()
    except Exception:  # noqa: BLE001
        scope_counts = {"TOTAL": 0, "PARTIAL": 0, "SOURCE_PENDING": 0, "NOT_STARTED": 0}
    return {
        "ok": False,
        "real_academic_readiness": False,
        "actionable_remediation": False,
        "failure_reason": revision.evidence_error or "SHA_ALIGNMENT_FAILED",
        "scope_ledger_counts": scope_counts,
        **revision.as_report_fields(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 16 verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    revision = resolve_revision_evidence(cwd=Path(__file__).resolve().parents[1])
    try:
        report = build_verification_report(revision=revision)
    except Exception as exc:  # noqa: BLE001
        report = {
            "ok": False,
            "failure_reason": f"verification_exception:{type(exc).__name__}",
            **revision.as_report_fields(),
        }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Day 16 verification:", "PASS" if report.get("ok") else "FAIL")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
