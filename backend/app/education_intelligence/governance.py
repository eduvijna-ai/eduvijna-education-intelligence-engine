from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml

_EXECUTION_STATE_ENV = "EDUVIJNA_EXECUTION_STATE_PATH"
_EXECUTION_STATE_RELATIVE = Path(".eduvijna") / "execution-state.yml"


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


def verify_governance_state(
    explicit_path: Path | str | None = None,
) -> dict[str, object]:
    path = resolve_execution_state_path(explicit_path)
    state = load_execution_state(path)
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
        "d5_ds01_status_deferred": day5.get("deferred_backlog_status")
        == "DEFERRED_BY_FOUNDER",
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "execution_state_path": str(path),
    }
