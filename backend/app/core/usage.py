from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIUsageRecord:
    provider: str
    model: str | None = None
    purpose: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None
