from __future__ import annotations

import time
from typing import Any

from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import (
    DraftQuestionItem,
    GenerationPlan,
    ResolvedScope,
    ReviewVerdict,
)
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationRequest
from app.orchestration.gateway_invoke import invoke_generation
from app.orchestration.nodes._helpers import (
    get_request,
    next_attempt,
    pipeline_failure,
    timed_update,
)
from app.orchestration.nodes.author import _target_item_ids
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def reviewers_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "reviewers")
    request = get_request(state)
    plan = GenerationPlan.model_validate(state.get("generation_plan") or {"items": []})
    targets = set(_target_item_ids(state, plan))
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    context = KnowledgeContextPack.model_validate(state.get("knowledge_context") or {})
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    roles = [
        (GenerationNodeRole.PATTERN_REVIEW, "pattern_review"),
        (GenerationNodeRole.CURRICULUM_REVIEW, "curriculum_review"),
        (GenerationNodeRole.EDUCATIONAL_REVIEW, "educational_review"),
    ]
    verdict_map: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in state.get("review_verdicts") or []:
        parsed = ReviewVerdict.model_validate(raw)
        verdict_map[(parsed.item_id, parsed.reviewer)] = raw
    gateway_usage = dict(state.get("gateway_usage") or {})
    call_cache = dict(state.get("generation_call_cache") or {})
    prompt_versions = dict(state.get("prompt_versions") or {})
    audit_refs: list[str] = []

    for draft in drafts:
        if draft.item_id not in targets:
            continue
        for role, prompt_name in roles:
            prompt = get_prompt(prompt_name)
            payload: dict[str, Any] = {
                "run_id": request.run_id,
                "item_id": draft.item_id,
                "draft": draft.model_dump(mode="json"),
                "canonical_scope": scope.model_dump(mode="json"),
            }
            if role == GenerationNodeRole.CURRICULUM_REVIEW:
                payload["day7_evidence"] = [
                    item.model_dump(mode="json") for item in context.evidence
                ]
                payload["citations"] = context.citations
                payload["bounded_context"] = context.bounded_text
            gen_request = GenerationRequest(
                role=role,
                prompt_version=prompt.version,
                system_prompt=prompt.text,
                user_payload=payload,
                output_schema_name="ReviewVerdict",
                scenario=request.fixture_scenario(),
            )
            response, extra = invoke_generation(
                deps,
                state,
                node_name="reviewers",
                attempt=attempt,
                request=gen_request,
                run_id=request.run_id,
                item_id=draft.item_id,
            )
            if extra and "error_code" in extra:
                failure = pipeline_failure(
                    deps, state, "reviewers", started, extra["error_code"], attempt=attempt
                )
                if extra.get("audit_refs"):
                    failure["audit_refs"] = list(failure.get("audit_refs") or []) + extra[
                        "audit_refs"
                    ]
                return failure
            assert response is not None
            if extra and extra.get("audit_refs"):
                audit_refs.extend(extra["audit_refs"])
            if extra and extra.get("cache"):
                call_cache = extra["cache"]
            gateway_usage = merge_gateway_usage(
                gateway_usage, response.usage, count_call=not bool(extra and extra.get("cache_hit"))
            )
            verdict = ReviewVerdict.model_validate(response.parsed)
            verdict_map[(verdict.item_id, verdict.reviewer)] = verdict.model_dump(mode="json")
            prompt_versions[prompt_name] = prompt.version

    return timed_update(
        state,
        "reviewers",
        started,
        {
            "review_verdicts": list(verdict_map.values()),
            "status": OrchestrationRunStatus.REVIEWING.value,
            "prompt_versions": prompt_versions,
            "gateway_usage": gateway_usage,
            "generation_call_cache": call_cache,
            "audit_refs": audit_refs,
        },
        attempt_map=attempt_map,
    )
