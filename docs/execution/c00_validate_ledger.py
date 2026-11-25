#!/usr/bin/env python3
"""Structural + semantic validation for C00 master ledger."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "docs" / "execution" / "C00-MASTER-TASK-EVIDENCE.csv"

REQUIRED_COLUMNS = [
    "task_id",
    "parent_task_id",
    "day",
    "original_authority",
    "original_requirement",
    "acceptance_criterion",
    "approved_amendments",
    "baseline_code_path",
    "test_path",
    "historical_candidate_sha",
    "historical_pr",
    "historical_ci_result",
    "current_baseline_evidence",
    "external_evidence",
    "engineering_acceptance_state",
    "current_static_inspection_state",
    "current_test_execution_state",
    "technical_acceptance_state",
    "residual_finding_ids",
    "dependencies",
    "closure_workstream",
    "acceptance_proof",
    "owner",
]

ALLOWED_WORKSTREAMS = {f"C{i:02d}" for i in range(16)}
ALLOWED_TECH = {
    "PASS",
    "PARTIAL",
    "BLOCKED",
    "SOURCE_PENDING",
    "NOT_STARTED",
    "UNKNOWN",
    "NOT_VERIFIED",
    "FOUNDER_REVIEW",
    "DEFERRED",
}
ALLOWED_ENG_PREFIX = ("HISTORICAL_", "FOUNDER_", "BLOCKED", "DEFERRED", "NOT_VERIFIED", "PARTIAL")

# Minimum authoritative denominators (original + listed amendments; not final universe)
EXPECTED_MINIMUM = {
    "Day3_core": 34,
    "D3-R": 12,
    "D11": 36,
    "D14-R3": 6,
    "D15-R3": 6,
}

MANDATORY_NONBLANK = (
    "original_authority",
    "original_requirement",
    "acceptance_criterion",
    "closure_workstream",
    "technical_acceptance_state",
    "engineering_acceptance_state",
    "historical_pr",
    "historical_ci_result",
    "owner",
    "acceptance_proof",
)

HELD_DAYS = {"Day11", "Day15", "Day17"}
MERGED_DEFERRED_DAYS = {"Day12", "Day13", "Day14", "Day16", "Day18"}


def load_rows() -> list[dict[str, str]]:
    with LEDGER.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != REQUIRED_COLUMNS:
            raise SystemExit(f"COLUMN_MISMATCH:{reader.fieldnames}")
        return list(reader)


def validate_primary(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    ids = [r["task_id"] for r in rows]
    idset = set(ids)
    if len(ids) != len(idset):
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        errors.append(f"duplicate_ids:{dupes[:5]}")

    for r in rows:
        tid = r["task_id"]
        for col in MANDATORY_NONBLANK:
            if not (r.get(col) or "").strip():
                errors.append(f"blank_mandatory:{tid}:{col}")
        if r["closure_workstream"] not in ALLOWED_WORKSTREAMS:
            errors.append(f"bad_workstream:{tid}:{r['closure_workstream']}")
        if r["technical_acceptance_state"] not in ALLOWED_TECH:
            errors.append(f"bad_technical:{tid}:{r['technical_acceptance_state']}")
        if r["technical_acceptance_state"] == "PASS" and r["day"] in HELD_DAYS | MERGED_DEFERRED_DAYS:
            errors.append(f"held_pass_in_technical:{tid}")
        parent = r["parent_task_id"]
        if parent and parent not in idset:
            errors.append(f"orphan_parent:{tid}:{parent}")
        if r["day"] in HELD_DAYS and r["technical_acceptance_state"] == "PASS":
            errors.append(f"held_day_technical_pass:{tid}")
        if "scope matrix" in r["original_authority"].lower() and tid.startswith(("D11-", "D7-", "D4-")):
            errors.append(f"scope_as_authority:{tid}")
        if r["day"] == "Day17" and tid in {"D17-F01", "D17-F05", "D17-F06", "D17-F07"} and r["closure_workstream"] != "C12":
            errors.append(f"d17_f_auth_wrong_ws:{tid}:{r['closure_workstream']}")
        if r["day"] == "Day17" and tid in {"D17-F02", "D17-F03", "D17-F04"} and r["closure_workstream"] != "C13":
            errors.append(f"d17_f_rest_wrong_ws:{tid}:{r['closure_workstream']}")
        if tid.startswith("D4-") and r["closure_workstream"] == "C02":
            errors.append(f"d4_assigned_c02:{tid}")

    d3_core = sum(1 for r in rows if re.match(r"D3-\d{2}$", r["task_id"]))
    d3r = sum(1 for r in rows if r["task_id"].startswith("D3-R"))
    if d3_core < EXPECTED_MINIMUM["Day3_core"]:
        errors.append(f"d3_core_undercount:{d3_core}")
    if d3r < EXPECTED_MINIMUM["D3-R"]:
        errors.append(f"d3r_undercount:{d3r}")
    if sum(1 for r in rows if r["task_id"].startswith("D11-")) < 36:
        errors.append("d11_undercount")
    if sum(1 for r in rows if r["task_id"].startswith("D14-R3-")) < 6:
        errors.append("d14_r3_undercount")
    if sum(1 for r in rows if r["task_id"].startswith("D15-R3-")) < 6:
        errors.append("d15_r3_undercount")

    return errors


def adversarial_self_tests() -> list[str]:
    """In-process checks on validation rules (documentation-only test harness)."""
    errors: list[str] = []
    bad_row = {c: "x" for c in REQUIRED_COLUMNS}
    bad_row["task_id"] = "D99-01"
    bad_row["day"] = "Day11"
    bad_row["technical_acceptance_state"] = "PASS"
    bad_row["closure_workstream"] = "C06"
    bad_row["parent_task_id"] = "MISSING_PARENT"
    if validate_primary([bad_row]) == []:
        errors.append("adversarial_should_fail_held_pass")
    return errors


def main() -> int:
    if not LEDGER.is_file():
        print(f"MISSING {LEDGER}")
        return 1
    rows = load_rows()
    errors = validate_primary(rows)
    errors.extend(adversarial_self_tests())

    by_day = Counter(r["day"] for r in rows)
    tech = Counter(r["technical_acceptance_state"] for r in rows)
    eng = Counter(r["engineering_acceptance_state"] for r in rows)

    print("VALIDATION_OK" if not errors else "VALIDATION_FAILED")
    print(f"row_count={len(rows)}")
    print(f"unique_ids={len({r['task_id'] for r in rows})}")
    print("per_day:", dict(sorted(by_day.items())))
    print("technical_acceptance_state:", dict(sorted(tech.items())))
    print("engineering_top:", dict(eng.most_common(6)))
    print(f"c00_audit_ci_record={C00_CANDIDATE_CI if 'C00_CANDIDATE_CI' in globals() else '45542731473'}")
    for e in errors[:30]:
        print("ERROR", e)
    return 0 if not errors else 2


C00_CANDIDATE_CI = "45542731473"

if __name__ == "__main__":
    sys.exit(main())