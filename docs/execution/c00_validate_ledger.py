#!/usr/bin/env python3
"""Validate C00-MASTER-TASK-EVIDENCE.csv structure and reconcile counts."""

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
    "HISTORICAL_ACCEPTED",
    "FOUNDER_MILESTONE_ONLY",
    "DEFERRED",
    "MISSING_SPEC",
    "",
}


def main() -> int:
    if not LEDGER.is_file():
        print(f"MISSING {LEDGER}")
        return 1

    with LEDGER.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != REQUIRED_COLUMNS:
            print("COLUMN_MISMATCH", reader.fieldnames)
            return 1
        rows = list(reader)

    errors: list[str] = []
    ids = [r["task_id"] for r in rows]
    if len(ids) != len(set(ids)):
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        errors.append(f"duplicate_ids:{dupes[:10]}")

    for r in rows:
        if not r["task_id"].strip():
            errors.append("empty_task_id")
        ws = r["closure_workstream"]
        if ws and ws not in ALLOWED_WORKSTREAMS:
            errors.append(f"bad_workstream:{r['task_id']}:{ws}")
        if r["technical_acceptance_state"] not in ALLOWED_TECH:
            errors.append(f"bad_state:{r['task_id']}:{r['technical_acceptance_state']}")

    by_day = Counter(r["day"] for r in rows)
    by_ws = Counter(r["closure_workstream"] for r in rows)

    print("VALIDATION_OK" if not errors else "VALIDATION_FAILED")
    print(f"row_count={len(rows)}")
    print(f"unique_ids={len(set(ids))}")
    print("per_day:", dict(sorted(by_day.items())))
    print("per_workstream:", dict(sorted(by_ws.items())))
    for e in errors[:20]:
        print("ERROR", e)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())