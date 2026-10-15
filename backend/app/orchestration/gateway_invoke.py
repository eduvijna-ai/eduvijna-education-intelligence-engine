from __future__ import annotations

from typing import Any

from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.gateway.types import (
    GenerationGatewayError,
    GenerationRequest,
    GenerationResponse,
)
from app.orchestration.model_calls import cached_response, call_cache_key, store_cached_response
from app.orchestration.nodes._helpers import audit_node
from app.orchestration.state import OrchestrationGraphState


def invoke_generation(
    deps: OrchestrationDependencies,
    state: OrchestrationGraphState,
    *,
    node_name: str,
    attempt: int,
    request: GenerationRequest,
    run_id: str,
    item_id: str | None,
) -> tuple[GenerationResponse | None, dict[str, Any] | None]:
    """Return (response, failure_update) where failure_update is set on gateway error."""
    cache = dict(state.get("generation_call_cache") or {})
    key = call_cache_key(
        run_id=run_id,
        role=request.role,
        item_id=item_id,
        prompt_version=request.prompt_version,
        payload=request.user_payload,
    )
    cached = cached_response(cache, key)
    if cached is not None:
        audit_id = audit_node(
            deps,
            state,
            node_name,
            "cache_hit",
            attempt=attempt,
            prompt_version=request.prompt_version,
            input_hash=key,
            payload={"item_id": item_id},
        )
        return cached, {"audit_refs": [audit_id]}
    try:
        response = deps.gateway.generate(request)
    except GenerationGatewayError as exc:
        audit_id = audit_node(
            deps,
            state,
            node_name,
            "failed",
            attempt=attempt,
            prompt_version=request.prompt_version,
            issue_codes=[exc.code],
            input_hash=key,
            payload={"item_id": item_id},
        )
        return None, {
            "error_code": exc.code,
            "input_hash": key,
            "audit_refs": [audit_id],
        }
    store_cached_response(cache, key, response)
    audit_id = audit_node(
        deps,
        state,
        node_name,
        "gateway_ok",
        attempt=attempt,
        prompt_version=request.prompt_version,
        gateway_request_id=response.gateway_request_id,
        input_hash=key,
        payload={"item_id": item_id},
    )
    state_cache_update = dict(cache)
    return response, {
        "cache": state_cache_update,
        "response": response,
        "input_hash": key,
        "audit_refs": [audit_id],
    }
