from __future__ import annotations

import time
from typing import Any

from app.orchestration.audit import persist_audit_event
from app.orchestration.control_session import commit_control
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import record_node_latency


def get_request(state: OrchestrationGraphState) -> OrchestrationRequest:
    return OrchestrationRequest.model_validate(state["request"])


def next_attempt(state: OrchestrationGraphState, node_name: str) -> tuple[int, dict[str, int]]:
    attempts = dict(state.get("node_attempts") or {})
    attempts[node_name] = attempts.get(node_name, 0) + 1
    return attempts[node_name], attempts


def audit_node(
    deps: Any,
    state: OrchestrationGraphState,
    node_name: str,
    status: str,
    *,
    attempt: int,
    issue_codes: list[str] | None = None,
    source_revision_ids: list[str] | None = None,
    prompt_version: str | None = None,
    gateway_request_id: str | None = None,
    input_hash: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    merged_payload = dict(payload or {})
    if input_hash:
        merged_payload["input_hash"] = input_hash
    event = persist_audit_event(
        deps.control_session,
        run_id=state["run_id"],
        request_hash=state.get("request_hash", ""),
        node_name=node_name,
        status=status,
        attempt=attempt,
        prompt_version=prompt_version,
        issue_codes=issue_codes,
        source_revision_ids=source_revision_ids,
        gateway_request_id=gateway_request_id,
        payload=merged_payload,
    )
    commit_control(deps.control_session)
    return str(event.id)


def pipeline_failure(
    deps: Any,
    state: OrchestrationGraphState,
    node_name: str,
    started: float,
    error_code: str,
    *,
    attempt: int,
    issue_codes: list[str] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    audit_id = audit_node(
        deps,
        state,
        node_name,
        "failed",
        attempt=attempt,
        issue_codes=issue_codes or [error_code],
    )
    errors = list(state.get("errors") or [])
    errors.append(error_code)
    status = (
        OrchestrationRunStatus.RETRY_REQUIRED.value
        if retryable
        else OrchestrationRunStatus.FAILED.value
    )
    update: dict[str, Any] = {
        "status": status,
        "errors": errors,
        "pipeline_halt": True,
        "audit_refs": [audit_id],
    }
    if retryable:
        update["gateway_retry_required"] = True
        update["gateway_retry_node"] = (
            "repair" if node_name == "repair_planner" else node_name
        )
    return timed_update(
        state,
        node_name,
        started,
        update,
        attempt_map={node_name: attempt},
    )


def timed_update(
    state: OrchestrationGraphState,
    node_name: str,
    started: float,
    update: dict[str, Any],
    *,
    attempt_map: dict[str, int] | None = None,
) -> dict[str, Any]:
    latency = (time.perf_counter() - started) * 1000
    update["node_latencies_ms"] = record_node_latency(
        state.get("node_latencies_ms"), node_name, latency
    )
    if attempt_map is not None:
        merged = dict(state.get("node_attempts") or {})
        merged.update(attempt_map)
        update["node_attempts"] = merged
    return update
