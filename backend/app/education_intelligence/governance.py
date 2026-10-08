from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


def load_execution_state() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / ".eduvijna" / "execution-state.yml"
    with path.open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


def verify_governance_state() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / ".eduvijna" / "execution-state.yml"
    with path.open(encoding="utf-8") as handle:
        state = cast(dict[str, Any], yaml.safe_load(handle))
    days = state.get("days", {})
    day5 = days.get(5, {})
    day6 = days.get(6, {})
    day7 = days.get(7, {})
    checks = {
        "current_day_is_6": state.get("current_day") == 6,
        "day6_active": day6.get("state") == "ACTIVE",
        "day6_not_founder_approved": day6.get("founder_approval") is False,
        "day7_locked": day7.get("state") == "LOCKED",
        "d5_ds01_deferred": day5.get("deferred_backlog") == "D5-DS01",
        "d5_ds01_issue_16": day5.get("deferred_issue") == 16,
        "d5_ds01_status_deferred": day5.get("deferred_backlog_status") == "DEFERRED_BY_FOUNDER",
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "execution_state_path": str(path),
    }
