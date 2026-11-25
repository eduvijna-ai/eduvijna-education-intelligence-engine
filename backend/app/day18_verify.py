"""Day 18 verification harness (D18-35)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED
from app.frontend_product.containment import (
    allowed_endpoints_file_integrity,
    catalogue_json_integrity,
    resolve_frontend_root,
    student_fixture_file_integrity,
    summarize_required_frontend_paths,
)
from app.frontend_product.governance import build_day18_governance_record
from app.frontend_product.scope_ledger import (
    load_repo_scope_counts,
    resolve_scope_map_path,
    validate_scope_map_integrity,
)
from app.verification.candidate_revision import resolve_revision_evidence


def build_verification_report(*, revision) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    scope_path = resolve_scope_map_path()
    scope_md = scope_path.read_text(encoding="utf-8")
    scope_integrity_ok, scope_issues = validate_scope_map_integrity(scope_md)
    scope_counts = load_repo_scope_counts()

    frontend_root = resolve_frontend_root()
    student_ok, student_issues = student_fixture_file_integrity(frontend_root)
    allowed_ok, allowed_issues = allowed_endpoints_file_integrity(frontend_root)
    catalogue_ok, catalogue_issues = catalogue_json_integrity(frontend_root)
    paths = summarize_required_frontend_paths(frontend_root)
    paths_ok = all(paths.values())

    containment_ok = student_ok and allowed_ok and catalogue_ok and paths_ok

    report_ok = (
        revision.sha_aligned
        and scope_integrity_ok
        and scope_counts.get("TOTAL") == 36
        and containment_ok
        and ACADEMIC_VALIDATION_DISABLED
        and ISSUANCE_DISABLED
    )

    return {
        "ok": report_ok,
        "governance": build_day18_governance_record(),
        "synthetic_demo_only": True,
        "ui_authority": "DENY_BY_DEFAULT",
        "real_learner_processing": False,
        "academic_generation_enabled": False,
        "day14_academic_validation_disabled": ACADEMIC_VALIDATION_DISABLED,
        "day14_issuance_disabled": ISSUANCE_DISABLED,
        "scope_map_integrity_ok": scope_integrity_ok,
        "scope_map_issues": list(scope_issues),
        "scope_ledger_counts": scope_counts,
        "frontend_paths": paths,
        "student_fixture_ok": student_ok,
        "student_fixture_issues": list(student_issues),
        "allowed_endpoints_ok": allowed_ok,
        "allowed_endpoint_issues": list(allowed_issues),
        "catalogue_ok": catalogue_ok,
        "catalogue_issues": list(catalogue_issues),
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "anythingllm_live": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "playwright_e2e": "LOCAL_OR_CI_FRONTEND",
            "d18_36_founder_signoff": "NOT_STARTED",
        },
        **revision.as_report_fields(),
    }


def _revision_failure_report(revision) -> dict[str, object]:
    try:
        scope_counts = load_repo_scope_counts()
    except Exception:  # noqa: BLE001
        scope_counts = {"TOTAL": 0, "PARTIAL": 0, "SOURCE_PENDING": 0, "NOT_STARTED": 0}
    return {
        "ok": False,
        "failure_reason": revision.evidence_error or "SHA_ALIGNMENT_FAILED",
        "synthetic_demo_only": True,
        "scope_ledger_counts": scope_counts,
        **revision.as_report_fields(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 18 verification harness")
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
        print("Day 18 verification:", "PASS" if report.get("ok") else "FAIL")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())