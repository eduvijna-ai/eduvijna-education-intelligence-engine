from __future__ import annotations

from typing import Any

from app.education_intelligence.governance import load_execution_state, resolve_execution_state_path


def verify_day7_governance_state(
    explicit_path: str | None = None,
) -> dict[str, object]:
    path = resolve_execution_state_path(explicit_path)
    state = load_execution_state(path)
    days = state.get("days", {})
    day5 = days.get(5, {})
    day7 = days.get(7, {})
    day8 = days.get(8, {})
    checks: dict[str, Any] = {
        "current_day_is_7": state.get("current_day") == 7,
        "day7_active": day7.get("state") == "ACTIVE",
        "day7_not_founder_approved": day7.get("founder_approval") is False,
        "day8_locked": day8.get("state") == "LOCKED",
        "d5_ds01_deferred": day5.get("deferred_backlog") == "D5-DS01",
        "d5_ds01_issue_16": day5.get("deferred_issue") == 16,
        "d5_ds01_status_deferred": day5.get("deferred_backlog_status")
        == "DEFERRED_BY_FOUNDER",
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "execution_state_path": str(path),
    }
