from __future__ import annotations

from typing import Any


def record_node_latency(
    existing: dict[str, float] | None, node_name: str, latency_ms: float
) -> dict[str, float]:
    merged = dict(existing or {})
    merged[node_name] = merged.get(node_name, 0.0) + latency_ms
    return merged


def merge_gateway_usage(
    existing: dict[str, Any] | None,
    gateway_usage: dict[str, Any],
    *,
    count_call: bool = True,
    role: str | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    if not count_call:
        merged["cache_hits"] = int(merged.get("cache_hits", 0)) + 1
        if role:
            by_role = dict(merged.get("cache_hits_by_role") or {})
            by_role[role] = int(by_role.get(role, 0)) + 1
            merged["cache_hits_by_role"] = by_role
        return merged
    increment = int(gateway_usage.get("model_calls", 0) or 0) or 1
    merged["model_calls"] = int(merged.get("model_calls", 0)) + increment
    merged["last_usage"] = gateway_usage
    tokens_in = gateway_usage.get("tokens_in")
    tokens_out = gateway_usage.get("tokens_out")
    if tokens_in is None and tokens_out is None:
        merged["token_usage_reported"] = False
    else:
        merged["token_usage_reported"] = True
    if role:
        by_role = dict(merged.get("model_calls_by_role") or {})
        by_role[role] = int(by_role.get(role, 0)) + increment
        merged["model_calls_by_role"] = by_role
    return merged
