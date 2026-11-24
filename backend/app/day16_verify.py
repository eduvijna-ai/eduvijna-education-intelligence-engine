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
from app.adaptive_remediation.fingerprint import fingerprint_from_plan
from app.adaptive_remediation.governance import build_day16_governance_record
from app.adaptive_remediation.integration_contracts import build_integration_bridge_status
from app.adaptive_remediation.internal_demo import build_authoritative_synthetic_plan
from app.adaptive_remediation.practice_plan import allocate_stage_counts, count_conservation_ok
from app.adaptive_remediation.prerequisite_plan import graph_ready
from app.adaptive_remediation.production_gate import explain_containment
from app.adaptive_remediation.scope_ledger import (
    load_repo_scope_counts,
    validate_scope_map_integrity,
)
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService
from app.adaptive_remediation.synthetic_fixture import INTERNAL_HISTORY
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED
from app.ca_imat_eapcet.enums import PlanVerdict
from app.ca_imat_eapcet.persistence_bridge import attempt_canonical_issuance
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def build_verification_report(*, revision: RevisionEvidence) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    scope_path = Path(__file__).resolve().parents[2] / "docs" / "execution" / "D16-SCOPE-MAP.md"
    scope_md = scope_path.read_text(encoding="utf-8")
    scope_integrity_ok, scope_issues = validate_scope_map_integrity(scope_md)
    scope_counts = load_repo_scope_counts()

    service = AdaptiveRemediationDiagnosticService()
    demo_a = service.run_authoritative_synthetic_demo()
    demo_b = build_authoritative_synthetic_plan()
    plan_replay_ok = (
        demo_a.fingerprint == demo_b.fingerprint
        and demo_a.stages == demo_b.stages
        and demo_a.targets == demo_b.targets
    )

    runtime_blocked = service.attempt_runtime_remediation()
    runtime_poison = service.attempt_runtime_remediation(session=object())
    runtime_ok = (
        runtime_blocked.planned_count == 0
        and runtime_poison.planned_count == 0
        and runtime_blocked.metadata_json.get("caller_data_processed") is False
        and "friction" not in runtime_poison.explanation.lower()
    )

    graph = build_friction_remediation_graph()
    g_ok, _, _ = graph_ready(graph)

    excluded = frozenset(INTERNAL_HISTORY.excluded_question_ids)
    counts_ok = {
        n: allocate_stage_counts(n, excluded_question_ids=excluded) is not None for n in (5, 10)
    }
    count_15_infeasible_with_exclusions = (
        allocate_stage_counts(15, excluded_question_ids=excluded) is None
    )
    count_20_infeasible = allocate_stage_counts(20, excluded_question_ids=excluded) is None

    conservation = (
        count_conservation_ok(demo_a.stages, demo_a.requested_count) if demo_a.stages else False
    )

    stages_have_all_three = len(demo_a.stages) >= 3 and {s.stage.value for s in demo_a.stages} >= {
        "foundation",
        "application",
        "target_retest",
    }
    newton_in_targets = any(t.concept_code == "newton-laws" for t in demo_a.targets)

    production_blocked = (
        PRODUCTION_REMEDIATION_DISABLED
        and not demo_a.production_gate.actionable
        and demo_a.production_gate.delivered_question_count == 0
        and demo_a.production_gate.validated_question_count == 0
        and demo_a.production_gate.scheduled_event_count == 0
    )

    day14_containment_unchanged = ACADEMIC_VALIDATION_DISABLED and ISSUANCE_DISABLED
    issuance = attempt_canonical_issuance(
        session=None,  # type: ignore[arg-type]
        questions=[],
        organization_id="d16-verify",
        institution_id="d16-verify",
        exam_version_id="synthetic",
        source_version="synthetic_demo",
        idempotency_key="d16-verify-empty",
    )
    issuance_contained = (
        not issuance.committed
        and issuance.verdict is PlanVerdict.NOT_READY
        and not issuance.persisted_question_ids
    )

    diagnostic_execution_ok = (
        revision.sha_aligned
        and scope_integrity_ok
        and scope_counts.get("TOTAL") == 36
        and g_ok
        and all(counts_ok.values())
        and count_15_infeasible_with_exclusions
        and count_20_infeasible
        and conservation
        and stages_have_all_three
        and newton_in_targets
        and production_blocked
        and runtime_ok
        and plan_replay_ok
        and SYNTHETIC_DIAGNOSTIC_ONLY
        and day14_containment_unchanged
        and issuance_contained
        and demo_a.verdict is not None
        and demo_a.verdict.value == "DIAGNOSTIC_PLAN"
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
            "verdict": demo_a.verdict.value,
            "planned_count": demo_a.planned_count,
            "selected_count": demo_a.selected_count,
            "stages": [s.stage.value for s in demo_a.stages],
            "fingerprint": fingerprint_from_plan(demo_a),
            "target_concepts": [t.concept_code for t in demo_a.targets],
        },
        "count_conservation_ok": conservation,
        "exact_count_checks": counts_ok,
        "count_15_infeasible_with_exclusions": count_15_infeasible_with_exclusions,
        "count_20_infeasible": count_20_infeasible,
        "runtime_entry_blocked": runtime_ok,
        "plan_replay_equal": plan_replay_ok,
        "scope_map_integrity_ok": scope_integrity_ok,
        "scope_map_issues": list(scope_issues),
        "integration_bridge": asdict(build_integration_bridge_status()),
        "dependency_closure": build_dependency_closure_register(),
        "scope_ledger_counts": scope_counts,
        "day14_academic_validation_disabled": ACADEMIC_VALIDATION_DISABLED,
        "day14_issuance_disabled": ISSUANCE_DISABLED,
        "day14_issuance_harness_contained": issuance_contained,
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
