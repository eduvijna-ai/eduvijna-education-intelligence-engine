#!/usr/bin/env python3
"""Adversarial mutation tests for c00_validate_ledger rules."""

from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "docs" / "execution" / "C00-MASTER-TASK-EVIDENCE.csv"

from c00_validate_ledger import REQUIRED_COLUMNS, validate_primary


def load_good_row() -> dict[str, str]:
    with LEDGER.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0]


def run_case(name: str, mutate) -> tuple[str, bool]:
    row = load_good_row()
    mutate(row)
    failed = bool(validate_primary([row]))
    return name, failed


def main() -> int:
    if not LEDGER.is_file():
        print("MISSING_LEDGER")
        return 1
    cases = [
        ("held_technical_pass", lambda r: (r.update({"task_id": "D11-99", "day": "Day11", "technical_acceptance_state": "PASS"}))),
        ("bad_workstream", lambda r: r.update({"closure_workstream": "C99"})),
        ("orphan_parent", lambda r: r.update({"parent_task_id": "D99-99"})),
        ("blank_mandatory", lambda r: r.update({"historical_pr": ""})),
        ("scope_as_authority_d11", lambda r: r.update({"task_id": "D11-99", "original_authority": "scope matrix only"})),
        ("d4_c02", lambda r: r.update({"task_id": "D4-01", "closure_workstream": "C02"})),
    ]
    errors: list[str] = []
    for name, mut in cases:
        _, failed = run_case(name, mut)
        if not failed:
            errors.append(f"adversarial_no_detect:{name}")
    print("ADVERSARIAL_OK" if not errors else "ADVERSARIAL_FAILED")
    for e in errors:
        print("ERROR", e)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())