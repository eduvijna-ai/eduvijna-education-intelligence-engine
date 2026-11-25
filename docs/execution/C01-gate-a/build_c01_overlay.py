#!/usr/bin/env python3
"""Gate A only: build C01 provisional-row overlay from C00 master CSV (no master rewrite)."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MASTER = ROOT / "docs/execution/C00-MASTER-TASK-EVIDENCE.csv"
OUT = Path(__file__).resolve().parent / "C01-FOUNDATION-RECONCILIATION-OVERLAY.csv"

EXTRA_OMISSIONS = [
    {
        "task_id": "C01-OMIT-PG0006",
        "original_authority": "docs/execution/D03-FINAL-COMPATIBILITY-CLOSURE.md",
        "original_requirement": "PostgreSQL-safe migration SQL (cross-dialect parity)",
        "gate_a_note": "Fresh disposable PG fails at 20261003_0006: SQLite boolean literal IS 1 in CHECK",
        "c01_disposition": "NEW_OBLIGATION_IDENTIFIED",
    },
    {
        "task_id": "C01-OMIT-0021-DATA",
        "original_authority": "docs/execution/D13-CLOSEOUT-RELEASE-GATES.md#RB-10",
        "original_requirement": "Populated 0020→0021 without silent untrusted marker promotion",
        "gate_a_note": "0021 CHECK requires all rows synthetic_test_only=1; absent/false rows fail on SQLite",
        "c01_disposition": "PREFLIGHT_REQUIRED_BEFORE_DDL",
    },
]


def main() -> None:
    rows = list(csv.DictReader(MASTER.open(encoding="utf-8")))
    c01 = [r for r in rows if r.get("closure_workstream") == "C01"]
    if len(c01) != 68:
        raise SystemExit(f"expected 68 C01 rows, found {len(c01)}")

    cols = [
        "task_id",
        "day",
        "original_authority",
        "acceptance_criterion",
        "baseline_code_path",
        "test_path",
        "historical_pr",
        "historical_ci_result",
        "c00_engineering_acceptance_state",
        "c01_gate_a_static_inspection",
        "c01_gate_a_execution",
        "c01_gate_a_disposition",
        "c01_evidence_ref",
        "residual_ids_preserved",
    ]
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in c01:
            w.writerow(
                {
                    "task_id": r["task_id"],
                    "day": r["day"],
                    "original_authority": r["original_authority"],
                    "acceptance_criterion": r["acceptance_criterion"],
                    "baseline_code_path": r["baseline_code_path"],
                    "test_path": r["test_path"],
                    "historical_pr": r["historical_pr"],
                    "historical_ci_result": r["historical_ci_result"],
                    "c00_engineering_acceptance_state": r["engineering_acceptance_state"],
                    "c01_gate_a_static_inspection": "PARTIAL: C00 ledger refs reconciled at 1781f036; no broad PASS",
                    "c01_gate_a_execution": "NOT_RUN: foundation recovery execution deferred to Gate B",
                    "c01_gate_a_disposition": "RECONCILED_PROVISIONAL_AWAITING_GATE_B",
                    "c01_evidence_ref": "docs/execution/C01-FOUNDATION-RECONCILIATION.md",
                    "residual_ids_preserved": "C00-R01..05;MS-001 unchanged",
                }
            )
        for extra in EXTRA_OMISSIONS:
            w.writerow(
                {
                    "task_id": extra["task_id"],
                    "original_authority": extra["original_authority"],
                    "acceptance_criterion": extra["original_requirement"],
                    "c01_gate_a_disposition": extra["c01_disposition"],
                    "c01_evidence_ref": "docs/execution/C01-GATE-A-DIAGNOSTICS.md",
                    "c01_gate_a_static_inspection": extra["gate_a_note"],
                }
            )
    print(f"wrote {OUT} rows={len(c01)+len(EXTRA_OMISSIONS)}")


if __name__ == "__main__":
    main()