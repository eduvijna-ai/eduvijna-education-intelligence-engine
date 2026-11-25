#!/usr/bin/env python3
"""Gate A only: C01 overlay with per-row static reconciliation (no C00 master rewrite)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MASTER = ROOT / "docs/execution/C00-MASTER-TASK-EVIDENCE.csv"
OUT = Path(__file__).resolve().parent / "C01-FOUNDATION-RECONCILIATION-OVERLAY.csv"
BASELINE = "1781f036d20cceae1d5fcc4b2c4e452e1e4530c7"

# Independent baseline refs at frozen develop (static only unless noted).
ROW_EVIDENCE: dict[str, dict[str, str]] = {
    "D1-DOD-05": {
        "baseline_code_path": "backend/migrations/env.py; backend/app/db/session.py",
        "test_path": "backend/tests/test_day3_rework_closure.py (SQLite fixtures)",
        "c01_gate_a_execution": "PASS disposable SQLite fresh head 0021 (harness)",
        "c01_gate_a_disposition": "PARTIAL: SQLite only; PG chain blocked",
    },
    "D1-DOD-06": {
        "baseline_code_path": "backend/app/db/session.py#create_database_engine",
        "test_path": "UNRESOLVED: no dedicated PG portability unit at baseline",
        "c01_gate_a_static_inspection": "SQLAlchemy URL abstraction present; live PG full chain FAIL 0006",
        "c01_gate_a_disposition": "PARTIAL",
    },
    "D1-DOD-07": {
        "baseline_code_path": "backend/migrations/versions/*.py",
        "test_path": "docs/execution/C01-gate-a/c01_gate_a_harness.py",
        "c01_gate_a_execution": "SQLite PASS; PG fresh FAIL before 0021",
        "c01_gate_a_disposition": "PARTIAL",
    },
    "D3-R11": {
        "baseline_code_path": "backend/migrations/versions/20261003_0007_day3_legacy_compatibility.py",
        "test_path": "backend/tests/test_day3_final_compatibility.py",
        "c01_gate_a_static_inspection": "Legacy evidence migration file present at baseline",
        "c01_gate_a_disposition": "RECONCILED_STATIC; runtime Gate B",
    },
    "D3-R12": {
        "baseline_code_path": "backend/app/models/source.py; backend/app/source_intelligence/service.py",
        "test_path": "backend/tests/test_source_intelligence.py",
        "c01_gate_a_static_inspection": "active_slot INTEGER + ck_source_revision_active_slot IS 1 (PG-unsafe)",
        "c01_gate_a_disposition": "PARTIAL portability finding C01-OMIT-PG0006",
    },
    "D13-31A": {
        "baseline_code_path": "backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py",
        "test_path": "UNRESOLVED: no isolated PG upgrade test at baseline",
        "c01_gate_a_static_inspection": "json_extract + synthetic_test_only=1 CHECK",
        "c01_gate_a_execution": "sqlite mixed EXPECTED_FAILURE; PG isolated 42883",
        "c01_gate_a_disposition": "PARTIAL + C01-OMIT-0021-DATA",
    },
}

PREFIX_STATIC: dict[str, tuple[str, str]] = {
    "D1-DOD": ("docs/execution/D01-FOUNDATION.md; backend/app/db/", "PARTIAL_STATIC"),
    "D2-DOD": ("backend/app/models/; backend/app/repositories/", "PARTIAL_STATIC"),
    "D3-R": ("backend/migrations/versions/20261003_*; backend/tests/test_day3_", "RECONCILED_STATIC_OR_PARTIAL"),
    "D13-": ("backend/migrations/versions/20261124_*; backend/app/models/day13_replay.py", "PARTIAL_PORTABILITY"),
    "D7-": ("backend/app/knowledge_intelligence/; backend/tests/test_day7_", "NOT_VERIFIED_RUNTIME_GATE_B"),
    "D9-": ("backend/app/examination/; backend/tests/test_day9_", "NOT_VERIFIED_RUNTIME_GATE_B"),
}

EXTRA_OMISSIONS = [
    {
        "task_id": "C01-OMIT-PG0006",
        "parent_task_id": "D3-R12",
        "day": "C01",
        "original_authority": "backend/migrations/versions/20261003_0006_day3_rework_closure.py",
        "acceptance_criterion": "PostgreSQL-safe CHECK for INTEGER active_slot",
        "baseline_code_path": "backend/app/models/source.py#ck_source_revision_active_slot",
        "test_path": "docs/execution/C01-gate-a/transcripts/*_active_slot_check_probe.log",
        "c01_gate_a_static_inspection": "IS 1 invalid on PG; proposed = 1 portable",
        "c01_gate_a_execution": "Probe PASS on disposable PG/SQLite",
        "c01_gate_a_disposition": "NEW_OBLIGATION; Founder approval before Gate B file list",
        "c01_evidence_ref": "docs/execution/C01-gate-a/C01-CHECK-CONSTRAINT-INVENTORY.md",
    },
    {
        "task_id": "C01-OMIT-0021-DATA",
        "parent_task_id": "D13-31A",
        "day": "C01",
        "original_authority": "backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py",
        "acceptance_criterion": "Strict JSON boolean preflight before DDL",
        "baseline_code_path": "backend/migrations/versions/20261124_0019..0021",
        "test_path": "docs/execution/C01-gate-a/transcripts/*_sqlite_marker_probes.log",
        "c01_gate_a_static_inspection": "json_extract conflates int 1 and true on SQLite",
        "c01_gate_a_execution": "Mixed markers FAIL at 0020 rollback",
        "c01_gate_a_disposition": "PREFLIGHT_REQUIRED; no data disposition authorized",
        "c01_evidence_ref": "docs/execution/C01-GATE-B-DECISION.md",
    },
]


def resolve_row(task_id: str, row: dict[str, str]) -> dict[str, str]:
    base = {
        "task_id": task_id,
        "parent_task_id": row.get("parent_task_id", ""),
        "day": row["day"],
        "original_authority": row["original_authority"],
        "acceptance_criterion": row["acceptance_criterion"],
        "baseline_code_path": row["baseline_code_path"],
        "test_path": row["test_path"],
        "historical_pr": row["historical_pr"],
        "historical_ci_result": row["historical_ci_result"],
        "c00_engineering_acceptance_state": row["engineering_acceptance_state"],
        "c01_gate_a_static_inspection": f"baseline@{BASELINE[:12]}: prior C00 NOT_VERIFIED unless keyed",
        "c01_gate_a_execution": "NOT_RUN",
        "c01_gate_a_disposition": "PROVISIONAL_UNCHANGED",
        "c01_evidence_ref": "docs/execution/C01-FOUNDATION-RECONCILIATION.md",
        "residual_ids_preserved": "C00-R01..05;MS-001",
    }
    if task_id in ROW_EVIDENCE:
        base.update(ROW_EVIDENCE[task_id])
    if row["baseline_code_path"].startswith("NOT_VERIFIED"):
        for prefix, (path_hint, disp) in PREFIX_STATIC.items():
            if task_id.startswith(prefix):
                base["baseline_code_path"] = f"develop@{BASELINE[:12]}: {path_hint}"
                base["c01_gate_a_disposition"] = disp
                base["c01_gate_a_static_inspection"] = (
                    f"NOT_VERIFIED@C00: prefix {prefix} static hint only"
                )
                break
        else:
            base["c01_gate_a_disposition"] = "PROVISIONAL_UNCHANGED"
    elif row["baseline_code_path"].strip() and row["baseline_code_path"] != "NOT_VERIFIED":
        base["baseline_code_path"] = row["baseline_code_path"]
        base["c01_gate_a_disposition"] = "PARTIAL_STATIC"
        if row.get("test_path") and row["test_path"] != "NOT_VERIFIED":
            base["test_path"] = row["test_path"]
    base["c01_evidence_ref"] = "docs/execution/C01-gate-a/transcripts/c01_gatea_3528d62e02f2_SUMMARY.json"
    return base


def main() -> None:
    rows = list(csv.DictReader(MASTER.open(encoding="utf-8")))
    c01 = [r for r in rows if r.get("closure_workstream") == "C01"]
    if len(c01) != 68:
        raise SystemExit(f"expected 68 C01 rows, found {len(c01)}")

    cols = [
        "task_id",
        "parent_task_id",
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
            w.writerow(resolve_row(r["task_id"], r))
        for extra in EXTRA_OMISSIONS:
            w.writerow(extra)
    print(f"wrote {OUT} rows={len(c01) + len(EXTRA_OMISSIONS)}")


if __name__ == "__main__":
    main()