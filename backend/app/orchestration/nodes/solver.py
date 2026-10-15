from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import DraftQuestionItem, SolverResult
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def solver_node(state: OrchestrationGraphState, deps: OrchestrationDependencies) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    prompt = get_prompt("solver")
    results: list[dict[str, Any]] = []
    gateway_usage = dict(state.get("gateway_usage") or {})

    for draft in drafts:
        stem_only = {
            "item_id": draft.item_id,
            "stem_text": draft.stem_text,
            "question_type": draft.question_type,
            "options": [{"option_key": o.option_key, "text": o.text} for o in draft.options],
        }
        try:
            response = deps.gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.SOLVER,
                    prompt_version=prompt.version,
                    system_prompt=prompt.text,
                    user_payload={
                        "run_id": request.run_id,
                        **stem_only,
                    },
                    output_schema_name="SolverResult",
                    scenario=request.fixture_scenario(),
                )
            )
        except GenerationGatewayError as exc:
            audit_node(deps, state, "solver", "failed", issue_codes=[exc.code])
            return timed_update(
                state,
                "solver",
                started,
                {"status": OrchestrationRunStatus.FAILED.value, "errors": [exc.code]},
            )
        gateway_usage = merge_gateway_usage(gateway_usage, response.usage)
        solver = SolverResult.model_validate(response.parsed)
        results.append(solver.model_dump(mode="json"))

    audit_node(deps, state, "solver", "ok")
    return timed_update(
        state,
        "solver",
        started,
        {
            "solver_results": results,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "prompt_versions": {**(state.get("prompt_versions") or {}), "solver": prompt.version},
            "gateway_usage": gateway_usage,
        },
    )
