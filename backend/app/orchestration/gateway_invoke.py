from __future__ import annotations

import hashlib
from typing import Any

from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.gateway.types import (
    GenerationGatewayError,
    GenerationRequest,
    GenerationResponse,
)
from app.orchestration.generation_call_store import (
    abandon_generation_call,
    claim_generation_call_start,
    complete_generation_call,
    load_call_status,
    load_persisted_call,
    mark_generation_call_ambiguous,
    mark_generation_call_invalid,
)
from app.orchestration.generation_output_validation import (
    GenerationOutputValidationError,
    validate_generation_output,
)
from app.orchestration.model_calls import cached_response, call_cache_key, store_cached_response
from app.orchestration.nodes._helpers import audit_node
from app.orchestration.state import OrchestrationGraphState


def chat_session_id_for_call(cache_key: str) -> str:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return f"eduvijna-{digest[:32]}"


def invoke_generation(
    deps: OrchestrationDependencies,
    state: OrchestrationGraphState,
    *,
    node_name: str,
    attempt: int,
    request: GenerationRequest,
    run_id: str,
    item_id: str | None,
    schema_payload_merge: dict[str, Any] | None = None,
) -> tuple[GenerationResponse | None, dict[str, Any] | None]:
    """Return (response, failure_update) where failure_update is set on gateway error."""
    control = deps.control_session
    cache = dict(state.get("generation_call_cache") or {})
    key = call_cache_key(
        run_id=run_id,
        role=request.role,
        item_id=item_id,
        prompt_version=request.prompt_version,
        payload=request.user_payload,
    )
    persisted = load_persisted_call(control, run_id=run_id, cache_key=key)
    if persisted is not None:
        store_cached_response(cache, key, persisted)
        audit_id = audit_node(
            deps,
            state,
            node_name,
            "cache_hit",
            attempt=attempt,
            prompt_version=request.prompt_version,
            input_hash=key,
            payload={"item_id": item_id, "source": "durable_store"},
        )
        return persisted, {"audit_refs": [audit_id], "cache_hit": True, "cache": cache}

    status = load_call_status(control, run_id=run_id, cache_key=key)
    allow_retry = bool(state.get("allow_gateway_retry"))
    if status in {"started", "ambiguous"}:
        if allow_retry and status == "started":
            abandon_generation_call(control, run_id=run_id, cache_key=key, commit=True)
        else:
            audit_id = audit_node(
                deps,
                state,
                node_name,
                "ambiguous",
                attempt=attempt,
                prompt_version=request.prompt_version,
                issue_codes=["gateway_call_ambiguous"],
                input_hash=key,
                payload={"item_id": item_id},
            )
            return None, {
                "error_code": "gateway_call_ambiguous",
                "retryable": True,
                "input_hash": key,
                "audit_refs": [audit_id],
            }

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
            payload={"item_id": item_id, "source": "graph_state"},
        )
        return cached, {"audit_refs": [audit_id], "cache_hit": True}

    if not claim_generation_call_start(control, run_id=run_id, cache_key=key, commit=True):
        audit_id = audit_node(
            deps,
            state,
            node_name,
            "ambiguous",
            attempt=attempt,
            prompt_version=request.prompt_version,
            issue_codes=["gateway_call_ambiguous"],
            input_hash=key,
        )
        return None, {
            "error_code": "gateway_call_ambiguous",
            "retryable": True,
            "input_hash": key,
            "audit_refs": [audit_id],
        }

    session_id = chat_session_id_for_call(key)
    enriched = GenerationRequest(
        role=request.role,
        prompt_version=request.prompt_version,
        system_prompt=request.system_prompt,
        user_payload=request.user_payload,
        output_schema_name=request.output_schema_name,
        scenario=request.scenario,
        workspace_slug=request.workspace_slug,
        model_settings=request.model_settings,
        chat_session_id=session_id,
        chat_reset=allow_retry,
    )
    try:
        response = deps.gateway.generate(enriched)
    except GenerationGatewayError as exc:
        mark_generation_call_ambiguous(control, run_id=run_id, cache_key=key, commit=True)
        audit_id = audit_node(
            deps,
            state,
            node_name,
            "failed",
            attempt=attempt,
            prompt_version=request.prompt_version,
            issue_codes=[exc.code],
            input_hash=key,
            payload={"item_id": item_id, "retryable": exc.retryable},
        )
        return None, {
            "error_code": exc.code,
            "retryable": exc.retryable,
            "input_hash": key,
            "audit_refs": [audit_id],
        }

    try:
        payload_for_schema = {**response.parsed, **(schema_payload_merge or {})}
        validated = validate_generation_output(request.output_schema_name, payload_for_schema)
    except GenerationOutputValidationError as exc:
        mark_generation_call_invalid(control, run_id=run_id, cache_key=key, commit=True)
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
            "retryable": False,
            "input_hash": key,
            "audit_refs": [audit_id],
        }

    safe_response = GenerationResponse(
        parsed=validated,
        raw_text="",
        latency_ms=response.latency_ms,
        gateway_request_id=response.gateway_request_id,
        usage=response.usage,
        call_context=response.call_context,
    )
    complete_generation_call(
        control,
        run_id=run_id,
        cache_key=key,
        structured_payload=validated,
        latency_ms=response.latency_ms,
        gateway_request_id=response.gateway_request_id,
        usage=response.usage,
        commit=True,
    )
    store_cached_response(cache, key, safe_response)
    audit_id = audit_node(
        deps,
        state,
        node_name,
        "gateway_ok",
        attempt=attempt,
        prompt_version=request.prompt_version,
        gateway_request_id=response.gateway_request_id,
        input_hash=key,
        payload={"item_id": item_id, "chat_session_id": session_id},
    )
    state_cache_update = dict(cache)
    return safe_response, {
        "cache": state_cache_update,
        "response": safe_response,
        "input_hash": key,
        "audit_refs": [audit_id],
    }
