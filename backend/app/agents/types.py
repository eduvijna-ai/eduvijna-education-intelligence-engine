from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentState:
    run_id: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    run_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
