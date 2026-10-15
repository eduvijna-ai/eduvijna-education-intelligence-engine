from __future__ import annotations

import time
from typing import Any

from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import DraftQuestionItem, GenerationPlan
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest
from app.orchestration.nodes._helpers import audit_node, get_request, timed_update
from app.orchestration.prompts.registry import get_prompt
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import merge_gateway_usage


def author_node(state: OrchestrationGraphState, deps: OrchestrationDependencies) -> dict[str, Any]:
    started = time.perf_counter()
    request = get_request(state)
    plan = GenerationPlan.model_validate(state.get("generation_plan") or {"items": []})
    context = KnowledgeContextPack.model_validate(
        state.get("knowledge_context")
        or {
            "query_text": "",
            "retrieval_profile_version": request.retrieval_profile_version,
            "query_id": "none",
            "evidence": [],
            "citations": [],
            "scope": {},
            "warnings": [],
            "bounded_text": "",
        }
    )
    allowed_revision_ids = [item.source_revision_id for item in context.evidence]
    lo_ids = request.metadata_json.get("learning_outcome_ids", [])
    if isinstance(lo_ids, str):
        lo_ids = [lo_ids]
    prompt = get_prompt("author")
    drafts: list[dict[str, Any]] = []
    gateway_usage = dict(state.get("gateway_usage") or {})
    errors: list[str] = []

    for slot in plan.items:
        repair_instructions = (state.get("repair_instructions_by_item") or {}).get(slot.item_id, [])
        try:
            response = deps.gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.AUTHOR,
                    prompt_version=prompt.version,
                    system_prompt=prompt.text,
                    user_payload={
                        "run_id": request.run_id,
                        "item_id": slot.item_id,
                        "allowed_source_revision_ids": allowed_revision_ids,
                        "learning_outcome_ids": lo_ids,
                        "marks": request.marks,
                        "bounded_context": context.bounded_text,
                        "repair_instructions": repair_instructions,
                        "foreign_revision_id": request.metadata_json.get("foreign_revision_id"),
                    },
                    output_schema_name="DraftQuestionItem",
                    scenario=request.fixture_scenario(),
                )
            )
        except GenerationGatewayError as exc:
            errors.append(exc.code)
            audit_node(deps, state, "author", "failed", issue_codes=[exc.code])
            return timed_update(
                state,
                "author",
                started,
                {
                    "status": OrchestrationRunStatus.FAILED.value,
                    "errors": [exc.code],
                },
            )
        gateway_usage = merge_gateway_usage(gateway_usage, response.usage)
        draft = DraftQuestionItem.model_validate({**response.parsed, "slot_index": slot.slot_index})
        drafts.append(draft.model_dump(mode="json"))

    audit_node(deps, state, "author", "ok", payload={"count": len(drafts)})
    return timed_update(
        state,
        "author",
        started,
        {
            "draft_items": drafts,
            "status": OrchestrationRunStatus.SOLVING.value,
            "prompt_versions": {**(state.get("prompt_versions") or {}), "author": prompt.version},
            "gateway_usage": gateway_usage,
            "errors": errors,
        },
    )
