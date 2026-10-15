from __future__ import annotations

from typing import Any

from app.education_intelligence.governance import load_execution_state, resolve_execution_state_path

_DAY8_HISTORICAL_IN_PROGRESS_STATES = frozenset(
    {
        "ACTIVE",
        "READY_FOR_REVIEW",
        "REVIEW_REQUIRED",
        "IN_PROGRESS",
    }
)


def _day5_deferred_checks(day5: dict[str, Any]) -> dict[str, bool]:
    return {
        "d5_ds01_deferred": day5.get("deferred_backlog") == "D5-DS01",
        "d5_ds01_issue_16": day5.get("deferred_issue") == 16,
        "d5_ds01_status_deferred": day5.get("deferred_backlog_status")
        == "DEFERRED_BY_FOUNDER",
    }


def verify_day7_governance_state(
    explicit_path: str | None = None,
) -> dict[str, object]:
    path = resolve_execution_state_path(explicit_path)
    state = load_execution_state(path)
    days = state.get("days", {})
    if not isinstance(days, dict):
        days = {}
    day5 = days.get(5, {}) if isinstance(days.get(5), dict) else {}
    day7 = days.get(7, {}) if isinstance(days.get(7), dict) else {}
    day8 = days.get(8, {}) if isinstance(days.get(8), dict) else {}

    current_day = state.get("current_day")
    deferred = _day5_deferred_checks(day5)

    if current_day == 7:
        checks: dict[str, object] = {
            "mode": "active_day7",
            "current_day_is_7": True,
            "day7_active": day7.get("state") == "ACTIVE",
            "day7_not_founder_approved": day7.get("founder_approval") is False,
            "day8_locked": day8.get("state") == "LOCKED",
            **deferred,
        }
    elif isinstance(current_day, int) and current_day >= 8:
        day8_state = day8.get("state")
        checks = {
            "mode": "historical_day7_regression",
            "current_day_ge_8": True,
            "day7_complete": day7.get("state") == "COMPLETE",
            "day7_founder_approved": day7.get("founder_approval") is True,
            "day8_legitimate_progress": isinstance(day8_state, str)
            and day8_state in _DAY8_HISTORICAL_IN_PROGRESS_STATES,
            **deferred,
        }
    else:
        checks = {
            "mode": "unsupported_phase",
            "current_day_is_7": current_day == 7,
            **deferred,
        }

    historical_mode = checks.get("mode") == "historical_day7_regression"
    pass_keys = {
        key
        for key in checks
        if key != "mode" and not (historical_mode and key == "current_day_is_7")
    }
    passed = all(checks[key] is True for key in pass_keys)

    return {
        "checks": checks,
        "passed": passed,
        "execution_state_path": str(path),
    }
