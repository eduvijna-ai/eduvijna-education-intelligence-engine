from __future__ import annotations

from typing import Any


def record_node_latency(
    existing: dict[str, float] | None, node_name: str, latency_ms: float
) -> dict[str, float]:
    merged = dict(existing or {})
    merged[node_name] = merged.get(node_name, 0.0) + latency_ms
    return merged


def _role_bucket(merged: dict[str, Any], role: str) -> dict[str, int]:
    attempts = dict(merged.get("gateway_attempts_by_role") or {})
    bucket = dict(attempts.get(role) or {"succeeded": 0, "failed": 0})
    attempts[role] = bucket
    merged["gateway_attempts_by_role"] = attempts
    return bucket


def _token_counts_bucket(merged: dict[str, Any], role: str) -> dict[str, int]:
    counts = dict(merged.get("token_usage_counts_by_role") or {})
    bucket = dict(counts.get(role) or {"reported": 0, "unknown": 0})
    counts[role] = bucket
    merged["token_usage_counts_by_role"] = counts
    return bucket


def record_gateway_role_attempt(
    existing: dict[str, Any] | None,
    role: str,
    *,
    succeeded: bool,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    bucket = _role_bucket(merged, role)
    if succeeded:
        bucket["succeeded"] = int(bucket.get("succeeded", 0)) + 1
    else:
        bucket["failed"] = int(bucket.get("failed", 0)) + 1
    return merged


def record_gateway_role_ambiguous(
    existing: dict[str, Any] | None,
    role: str,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    ambiguous = dict(merged.get("gateway_ambiguous_by_role") or {})
    ambiguous[role] = int(ambiguous.get(role, 0)) + 1
    merged["gateway_ambiguous_by_role"] = ambiguous
    return merged


def record_diagnostic_tag_repair(
    existing: dict[str, Any] | None,
    *,
    count: int = 1,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing or {})
    prior = int(merged.get("diagnostic_tag_repair_calls", 0))
    merged["diagnostic_tag_repair_calls"] = prior + count
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
    tokens_by_role = dict(merged.get("token_usage_reported_by_role") or {})
    if role:
        token_bucket = _token_counts_bucket(merged, role)
        if tokens_in is None and tokens_out is None:
            token_bucket["unknown"] = int(token_bucket.get("unknown", 0)) + 1
            tokens_by_role[role] = "unknown"
        else:
            token_bucket["reported"] = int(token_bucket.get("reported", 0)) + 1
            tokens_by_role[role] = True
        merged["token_usage_reported_by_role"] = tokens_by_role
    if tokens_in is None and tokens_out is None:
        merged["token_usage_reported"] = False
    else:
        merged["token_usage_reported"] = True
    if role:
        by_role = dict(merged.get("model_calls_by_role") or {})
        by_role[role] = int(by_role.get(role, 0)) + increment
        merged["model_calls_by_role"] = by_role
        record_gateway_role_attempt(merged, role, succeeded=True)
    return merged
