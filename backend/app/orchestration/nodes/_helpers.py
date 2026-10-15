from __future__ import annotations

import time
from typing import Any

from app.orchestration.audit import persist_audit_event
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.state import OrchestrationGraphState
from app.orchestration.usage import record_node_latency


def get_request(state: OrchestrationGraphState) -> OrchestrationRequest:
    return OrchestrationRequest.model_validate(state["request"])


def bump_attempt(state: OrchestrationGraphState, node_name: str) -> dict[str, int]:
    attempts = dict(state.get("node_attempts") or {})
    attempts[node_name] = attempts.get(node_name, 0) + 1
    return attempts


def audit_node(
    deps: Any,
    state: OrchestrationGraphState,
    node_name: str,
    status: str,
    *,
    issue_codes: list[str] | None = None,
    source_revision_ids: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    persist_audit_event(
        deps.session,
        run_id=state["run_id"],
        request_hash=state.get("request_hash", ""),
        node_name=node_name,
        status=status,
        attempt=(state.get("node_attempts") or {}).get(node_name, 1),
        issue_codes=issue_codes,
        source_revision_ids=source_revision_ids,
        payload=payload,
    )


def timed_update(
    state: OrchestrationGraphState,
    node_name: str,
    started: float,
    update: dict[str, Any],
) -> dict[str, Any]:
    latency = (time.perf_counter() - started) * 1000
    update["node_latencies_ms"] = record_node_latency(
        state.get("node_latencies_ms"), node_name, latency
    )
    update["node_attempts"] = bump_attempt(state, node_name)
    return update
