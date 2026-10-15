from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HumanResumeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "edit"]
    actor_id: str | None = None
    reason: str | None = None
    item_patches: dict[str, dict[str, Any]] = Field(default_factory=dict)
