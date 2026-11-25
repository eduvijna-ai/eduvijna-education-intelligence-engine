from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UuidPath(StrictModel):
    id: UUID


class PaginationQuery(StrictModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaginatedMeta(StrictModel):
    limit: int
    offset: int
    total: int


class CapabilityItem(StrictModel):
    code: str
    disposition: str
    reason: str
    scopes: list[str]


class CapabilityListResponse(StrictModel):
    capabilities: list[CapabilityItem]
    containment: dict[str, bool]


class JobResponse(StrictModel):
    id: UUID
    status: str
    capability_code: str
    created_at: datetime
    updated_at: datetime
    progress: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    synthetic_fixture_only: bool = False
