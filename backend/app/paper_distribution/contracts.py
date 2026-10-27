from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.education_intelligence.taxonomy_registry import V1_TAXONOMY_VERSION
from app.paper_distribution.enums import (
    DistributionDimensionStatus,
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)


class PaperItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    marks: float | None = None
    cognitive_level: str | None = None
    competency_codes: list[str] = Field(default_factory=list)
    primary_competency_code: str | None = None
    day6_validated: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DistributionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    key: str
    exact_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    min_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    max_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    exact_count: int | None = Field(default=None, ge=0)


class PaperDistributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    taxonomy_version: str = V1_TAXONOMY_VERSION
    requested_count: int | None = Field(default=None, ge=0)
    items: list[PaperItemInput]
    cognitive_targets: list[DistributionTarget] = Field(default_factory=list)
    competency_targets: list[DistributionTarget] = Field(default_factory=list)
    multi_label_policy: MultiLabelPolicy = MultiLabelPolicy.PRIMARY_ONLY
    include_mark_weighted: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DimensionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    counts: dict[str, int] = Field(default_factory=dict)
    fractional_counts: dict[str, float] = Field(default_factory=dict)
    count_percent: dict[str, float] = Field(default_factory=dict)
    mark_weighted_percent: dict[str, float] = Field(default_factory=dict)
    missing_coverage: list[str] = Field(default_factory=list)
    status: DistributionDimensionStatus = DistributionDimensionStatus.PASS
    variance: dict[str, float] = Field(default_factory=dict)


class PaperDistributionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    verdict: PaperDistributionVerdict
    item_count: int
    distinct_item_ids: list[str]
    cognitive_summary: DimensionSummary
    competency_summary: DimensionSummary
    issue_codes: list[PaperDistributionIssueCode] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)
    audit_ref: str | None = None
    result_fingerprint: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
