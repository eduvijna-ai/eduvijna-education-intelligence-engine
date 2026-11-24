"""Day 17 verification harness (D17-35)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.adaptive_remediation.containment import PRODUCTION_REMEDIATION_DISABLED
from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED
from app.platform.capability_registry import containment_snapshot, list_capabilities
from app.platform.dependency_closure import build_day17_dependency_closure_register
from app.platform.governance import build_day17_governance_record
from app.platform.mcp.tools import mcp_get_capabilities, mcp_tool_router
from app.platform.security.limits import security_limits_snapshot
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def _scope_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "docs" / "execution" / "D17-SCOPE-MAP.md"


def _count_scope_rows(text: str) -> dict[str, int]:
    rows = re.findall(r"^\| D17-\d{2} \|", text, flags=re.MULTILINE)
    statuses = {
        "PASS": len(re.findall(r"\| PASS \|", text)),
        "PARTIAL": len(re.findall(r"\| PARTIAL \|", text)),
        "BLOCKED": len(re.findall(r"\| BLOCKED \|", text)),
        "NOT_STARTED": len(re.findall(r"\| NOT_STARTED \|", text)),
    }
    statuses["TOTAL"] = len(rows)
    return statuses


def build_verification_report(*, revision: RevisionEvidence) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return {
            "ok": False,
            "reason": revision.evidence_error or "sha_not_aligned",
            "candidate_sha": revision.candidate_sha,
            "head_sha": revision.observed_sha,
        }

    scope_path = _scope_path()
    scope_md = scope_path.read_text(encoding="utf-8") if scope_path.is_file() else ""
    scope_counts = _count_scope_rows(scope_md) if scope_md else {"TOTAL": 0}

    caps = list_capabilities()
    containment_ok = (
        ACADEMIC_VALIDATION_DISABLED
        and ISSUANCE_DISABLED
        and PRODUCTION_REMEDIATION_DISABLED
        and containment_snapshot()["day15_learner_hold"]
    )

    learner_blocked = False
    remediation_blocked = False
    try:
        mcp_tool_router("get_learner_diagnostics", {})
    except Exception:
        learner_blocked = True
    try:
        mcp_tool_router("recommend_remediation", {})
    except Exception:
        remediation_blocked = True

    mcp_caps = mcp_get_capabilities()
    limits = security_limits_snapshot()

    ok = (
        revision.sha_aligned
        and scope_counts.get("TOTAL") == 36
        and len(caps) >= 10
        and containment_ok
        and learner_blocked
        and remediation_blocked
        and isinstance(mcp_caps.get("containment"), dict)
        and limits.get("rate_limit_distributed") is False
    )

    return {
        "ok": ok,
        "candidate_sha": revision.candidate_sha,
        "governance": build_day17_governance_record(),
        "dependency_closure": build_day17_dependency_closure_register(),
        "scope_counts": scope_counts,
        "capability_count": len(caps),
        "containment_ok": containment_ok,
        "learner_mcp_blocked": learner_blocked,
        "remediation_mcp_blocked": remediation_blocked,
        "live_postgresql_migration_0021": "NOT_RUN_DEFERRED_BLOCKER",
        "compose_smoke": "NOT_RUN",
        "day18_state": "LOCKED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 17 exact-HEAD verifier")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    revision = resolve_revision_evidence()
    report = build_verification_report(revision=revision)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("ok=" + str(report.get("ok")))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
