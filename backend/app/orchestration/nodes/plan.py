from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import GenerationPlan, GenerationPlanItem
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.state import OrchestrationGraphState


def plan_generation_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    items = [
        GenerationPlanItem(item_id=f"{request.run_id}-slot-{index}", slot_index=index)
        for index in range(request.requested_count)
    ]
    plan = GenerationPlan(items=items, requested_count=request.requested_count)
    audit_node(deps, state, "plan_generation", "ok", payload={"count": request.requested_count})
    return timed_update(
        state,
        "plan_generation",
        started,
        {
            "generation_plan": plan.model_dump(mode="json"),
            "status": OrchestrationRunStatus.AUTHORING.value,
        },
    )
