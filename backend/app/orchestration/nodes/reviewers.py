from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import DraftQuestionItem, ReviewVerdict
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def _review_role(role: GenerationNodeRole, prompt_name: str) -> tuple[GenerationNodeRole, str]:
    return role, prompt_name


def reviewers_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    roles = [
        _review_role(GenerationNodeRole.PATTERN_REVIEW, "pattern_review"),
        _review_role(GenerationNodeRole.CURRICULUM_REVIEW, "curriculum_review"),
        _review_role(GenerationNodeRole.EDUCATIONAL_REVIEW, "educational_review"),
    ]
    verdicts: list[dict[str, Any]] = []
    gateway_usage = dict(state.get("gateway_usage") or {})
    prompt_versions = dict(state.get("prompt_versions") or {})

    for draft in drafts:
        for role, prompt_name in roles:
            prompt = get_prompt(prompt_name)
            try:
                response = deps.gateway.generate(
                    GenerationRequest(
                        role=role,
                        prompt_version=prompt.version,
                        system_prompt=prompt.text,
                        user_payload={
                            "run_id": request.run_id,
                            "item_id": draft.item_id,
                            "draft": draft.model_dump(mode="json"),
                        },
                        output_schema_name="ReviewVerdict",
                        scenario=request.fixture_scenario(),
                    )
                )
            except GenerationGatewayError as exc:
                return timed_update(
                    state,
                    "reviewers",
                    started,
                    {"status": OrchestrationRunStatus.FAILED.value, "errors": [exc.code]},
                )
            gateway_usage = merge_gateway_usage(gateway_usage, response.usage)
            verdict = ReviewVerdict.model_validate(response.parsed)
            verdicts.append(verdict.model_dump(mode="json"))
            prompt_versions[prompt_name] = prompt.version

    audit_node(deps, state, "reviewers", "ok", payload={"verdict_count": len(verdicts)})
    return timed_update(
        state,
        "reviewers",
        started,
        {
            "review_verdicts": verdicts,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "prompt_versions": prompt_versions,
            "gateway_usage": gateway_usage,
        },
    )
