from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml

_EXECUTION_STATE_ENV = "EDUVIJNA_EXECUTION_STATE_PATH"
_EXECUTION_STATE_RELATIVE = Path(".eduvijna") / "execution-state.yml"
_DAY7_ACTIVE_PHASE_STATES = frozenset({"ACTIVE", "FOUNDER_REVIEW", "COMPLETE"})


def resolve_execution_state_path(explicit_path: Path | str | None = None) -> Path:
    """Resolve the governance file in checkout and container layouts.

    Local/backend CI runs from the repository checkout, while Docker runs the
    backend from /app. Prefer an explicit path (or environment override), then
    check both the current working directory and source-relative repository
    layouts. Fail with all attempted paths instead of silently reading the wrong
    governance file.
    """
    candidates: list[Path] = []

    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured = os.getenv(_EXECUTION_STATE_ENV)
    if configured:
        candidates.append(Path(configured))

    source_path = Path(__file__).resolve()
    candidates.extend(
        [
            Path.cwd() / _EXECUTION_STATE_RELATIVE,
            source_path.parents[3] / _EXECUTION_STATE_RELATIVE,
            source_path.parents[2] / _EXECUTION_STATE_RELATIVE,
        ]
    )

    attempted: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        attempted.append(str(candidate))
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "Eduvijna execution state not found; checked: " + ", ".join(attempted)
    )


def load_execution_state(
    explicit_path: Path | str | None = None,
) -> dict[str, Any]:
    path = resolve_execution_state_path(explicit_path)
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Execution state must be a mapping: {path}")
    return cast(dict[str, Any], payload)


def _day5_deferred_checks(day5: dict[str, Any]) -> dict[str, bool]:
    return {
        "d5_ds01_deferred": day5.get("deferred_backlog") == "D5-DS01",
        "d5_ds01_issue_16": day5.get("deferred_issue") == 16,
        "d5_ds01_status_deferred": day5.get("deferred_backlog_status")
        == "DEFERRED_BY_FOUNDER",
    }


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _historical_day6_record_checks(day6: dict[str, Any]) -> dict[str, bool]:
    return {
        "day6_complete": day6.get("state") == "COMPLETE",
        "day6_founder_approved": day6.get("founder_approval") is True,
        "day6_review_status_complete_clean": day6.get("review_status") == "COMPLETE_CLEAN",
        "day6_engineering_ci_green": day6.get("engineering_ci_status") == "GREEN",
        "day6_merge_commit_present": _non_empty_string(day6.get("merge_commit")),
        "day6_codex_review_clean": day6.get("codex_review_result")
        == "CLEAN_NO_MAJOR_ISSUES",
        "day6_codex_reviewed_commit_present": _non_empty_string(
            day6.get("codex_reviewed_commit")
        ),
    }


def _day7_phase_checks(current_day: int, day7: dict[str, Any]) -> dict[str, bool]:
    state = day7.get("state")
    if current_day == 7:
        valid = isinstance(state, str) and state in _DAY7_ACTIVE_PHASE_STATES
    elif current_day > 7:
        valid = state == "COMPLETE" and day7.get("founder_approval") is True
    else:
        valid = False
    return {"day7_phase_valid": valid}


def verify_governance_state(
    explicit_path: Path | str | None = None,
) -> dict[str, object]:
    path = resolve_execution_state_path(explicit_path)
    state = load_execution_state(path)
    days = state.get("days", {})
    if not isinstance(days, dict):
        days = {}
    day5 = days.get(5, {}) if isinstance(days.get(5), dict) else {}
    day6 = days.get(6, {}) if isinstance(days.get(6), dict) else {}
    day7 = days.get(7, {}) if isinstance(days.get(7), dict) else {}

    current_day = state.get("current_day")
    if current_day == 6:
        checks: dict[str, object] = {
            "mode": "active_day6",
            "current_day_is_6": True,
            "day6_active": day6.get("state") == "ACTIVE",
            "day6_not_founder_approved": day6.get("founder_approval") is False,
            "day7_locked": day7.get("state") == "LOCKED",
            **_day5_deferred_checks(day5),
        }
    elif isinstance(current_day, int) and current_day > 6:
        checks = {
            "mode": "historical_day6_complete",
            "current_day_is_6": False,
            **_historical_day6_record_checks(day6),
            **_day7_phase_checks(current_day, day7),
            **_day5_deferred_checks(day5),
        }
    else:
        checks = {
            "mode": "unsupported_phase",
            "current_day_is_6": current_day == 6,
            **_day5_deferred_checks(day5),
        }

    historical_mode = checks.get("mode") == "historical_day6_complete"
    pass_keys = {
        key
        for key in checks
        if key != "mode" and not (historical_mode and key == "current_day_is_6")
    }
    passed = all(checks[key] is True for key in pass_keys)
    return {
        "checks": checks,
        "passed": passed,
        "execution_state_path": str(path),
    }
