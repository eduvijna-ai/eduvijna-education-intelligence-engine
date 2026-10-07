"""CI-only helper for Day 5 official evidence: never greenwash verifier crashes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ENGINEERING_BLOCKER_FIELDS = (
    "manifest_identity_blockers",
    "manifest_classification_blockers",
)


def _founder_deferred_ds01(execution_state_path: Path) -> bool:
    if not execution_state_path.is_file():
        return False
    text = execution_state_path.read_text(encoding="utf-8")
    return (
        "deferred_backlog: D5-DS01" in text
        and "deferred_backlog_status: DEFERRED_BY_FOUNDER" in text
    )


def _load_structured_report(report_path: Path) -> dict[str, Any] | None:
    if not report_path.is_file() or report_path.stat().st_size == 0:
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _engineering_sound(report: dict[str, Any]) -> bool:
    acceptance = report.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("passed") is not False:
        return False
    for field in _ENGINEERING_BLOCKER_FIELDS:
        blockers = report.get(field)
        if blockers is None:
            return False
        if not isinstance(blockers, list) or blockers:
            return False
    accounting = report.get("manifest_accounting")
    if not isinstance(accounting, dict):
        return False
    expected = accounting.get("required_academic_expected_count")
    present = accounting.get("required_academic_present_count")
    required_count = accounting.get("required_academic_count")
    supplemental = accounting.get("supplemental_authority_count")
    distinct = accounting.get("manifest_validated_distinct")
    if not all(
        isinstance(value, int)
        for value in (expected, present, required_count, supplemental, distinct)
    ):
        return False
    assert isinstance(expected, int)
    assert isinstance(present, int)
    assert isinstance(required_count, int)
    assert isinstance(supplemental, int)
    assert isinstance(distinct, int)
    exp, pres, req, supp, dist = expected, present, required_count, supplemental, distinct
    if exp != pres or exp != req:
        return False
    if dist != exp + supp:
        return False
    sources = report.get("sources")
    if not isinstance(sources, list) or not sources:
        return False
    if not isinstance(report.get("public_artifact_contains"), str):
        return False
    return True


def resolve_ci_exit_code(
    verifier_exit: int,
    report_path: Path,
    *,
    execution_state_path: Path,
) -> int:
    """Return process exit code for the day5-official-evidence CI step."""
    if verifier_exit == 0:
        return 0
    report = _load_structured_report(report_path)
    if report is None:
        return verifier_exit if verifier_exit != 0 else 1
    if not _engineering_sound(report):
        return verifier_exit if verifier_exit != 0 else 1
    if not _founder_deferred_ds01(execution_state_path):
        return verifier_exit if verifier_exit != 0 else 1
    print(
        "::warning::Day 5 authoritative source gate remains fail-closed "
        "(acceptance=false); D5-DS01 is Founder-deferred. "
        f"Verifier exit code: {verifier_exit}. Metadata artifact uploaded.",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--verifier-exit", type=int, required=True)
    parser.add_argument(
        "--execution-state",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".eduvijna" / "execution-state.yml",
    )
    args = parser.parse_args()
    raise SystemExit(
        resolve_ci_exit_code(
            args.verifier_exit,
            args.report,
            execution_state_path=args.execution_state,
        )
    )


if __name__ == "__main__":
    main()
