from __future__ import annotations

import time
from typing import Any

from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, next_attempt, timed_update
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import record_diagnostic_tag_repair


def diagnostic_repair_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "diagnostic_repair")
    diagnostic = state.get("diagnostic_validation") or []
    repair_counts = dict(state.get("repair_count_by_item") or {})
    item_ids: list[str] = []
    for summary in diagnostic:
        if not summary.get("repairable"):
            continue
        item_id = str(summary.get("item_id"))
        item_ids.append(item_id)
        repair_counts[item_id] = repair_counts.get(item_id, 0) + 1

    audit_id = audit_node(
        deps,
        state,
        "diagnostic_repair",
        "ok",
        attempt=attempt,
        payload={"items": item_ids, "tag_only": True},
    )
    gateway_usage = record_diagnostic_tag_repair(
        state.get("gateway_usage"),
        count=len(item_ids),
    )
    return timed_update(
        state,
        "diagnostic_repair",
        started,
        {
            "diagnostic_tag_repair_item_ids": item_ids,
            "repair_count_by_item": repair_counts,
            "gateway_usage": gateway_usage,
            "status": OrchestrationRunStatus.REPAIRING.value,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
