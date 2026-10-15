from __future__ import annotations

from typing import Any


def record_node_latency(
    existing: dict[str, float] | None, node_name: str, latency_ms: float
) -> dict[str, float]:
    merged = dict(existing or {})
    merged[node_name] = merged.get(node_name, 0.0) + latency_ms
    return merged


def merge_gateway_usage(
    existing: dict[str, Any] | None, gateway_usage: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    calls = int(merged.get("model_calls", 0)) + int(gateway_usage.get("model_calls", 0))
    merged["model_calls"] = calls
    merged["last_usage"] = gateway_usage
    return merged
