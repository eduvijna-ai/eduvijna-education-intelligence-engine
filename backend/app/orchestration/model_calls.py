from __future__ import annotations

import hashlib
import json
from typing import Any

from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.types import GenerationResponse


def call_cache_key(
    *,
    run_id: str,
    role: GenerationNodeRole,
    item_id: str | None,
    prompt_version: str,
    payload: dict[str, Any],
) -> str:
    encoded = json.dumps(
        {
            "run_id": run_id,
            "role": role.value,
            "item_id": item_id,
            "prompt_version": prompt_version,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def cached_response(
    cache: dict[str, Any] | None, key: str
) -> GenerationResponse | None:
    if not cache:
        return None
    raw = cache.get(key)
    if not isinstance(raw, dict):
        return None
    return GenerationResponse(
        parsed=raw["parsed"],
        raw_text=raw["raw_text"],
        latency_ms=float(raw.get("latency_ms", 0)),
        gateway_request_id=raw.get("gateway_request_id"),
        usage=dict(raw.get("usage") or {}),
    )


def store_cached_response(cache: dict[str, Any], key: str, response: GenerationResponse) -> None:
    cache[key] = {
        "parsed": response.parsed,
        "raw_text": response.raw_text,
        "latency_ms": response.latency_ms,
        "gateway_request_id": response.gateway_request_id,
        "usage": response.usage,
    }
