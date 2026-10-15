from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import ReviewVerdict
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationRequest
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState


def repair_planner_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    verdicts = [ReviewVerdict.model_validate(v) for v in state.get("review_verdicts") or []]
    repair_instructions: dict[str, list[str]] = {}
    for verdict in verdicts:
        if not verdict.repair_instructions:
            continue
        repair_instructions.setdefault(verdict.item_id, []).extend(verdict.repair_instructions)

    deterministic = state.get("deterministic_validation") or []
    for summary in deterministic:
        if summary.get("repairable"):
            item_id = str(summary.get("item_id"))
            repair_instructions.setdefault(item_id, []).append(
                "Address deterministic validation findings: "
                + ",".join(summary.get("issue_codes") or [])
            )

    repair_counts = dict(state.get("repair_count_by_item") or {})
    for item_id in repair_instructions:
        repair_counts[item_id] = repair_counts.get(item_id, 0) + 1

    prompt = get_prompt("repair")
    deps.gateway.generate(
        GenerationRequest(
            role=GenerationNodeRole.REPAIR,
            prompt_version=prompt.version,
            system_prompt=prompt.text,
            user_payload={"repair_instructions": repair_instructions},
            output_schema_name="RepairPlan",
            scenario=request.fixture_scenario(),
        )
    )
    audit_node(deps, state, "repair_planner", "ok", payload={"items": list(repair_instructions)})
    return timed_update(
        state,
        "repair_planner",
        started,
        {
            "repair_instructions_by_item": repair_instructions,
            "repair_count_by_item": repair_counts,
            "status": OrchestrationRunStatus.REPAIRING.value,
        },
    )
