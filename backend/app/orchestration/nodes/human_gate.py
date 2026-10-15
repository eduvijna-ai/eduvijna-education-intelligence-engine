from __future__ import annotations

import time
from typing import Any

from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, timed_update
from app.orchestration.state import OrchestrationGraphState


def human_gate_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "repair_count_by_item": state.get("repair_count_by_item") or {},
        "deterministic_validation": state.get("deterministic_validation") or [],
    }
    audit_node(deps, state, "human_gate", "paused", payload=payload)
    return timed_update(
        state,
        "human_gate",
        started,
        {
            "interrupt_payload": payload,
            "status": OrchestrationRunStatus.REVIEW_REQUIRED.value,
        },
    )
