from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)


class SourceRegistrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    title: str = Field(min_length=1, max_length=512)
    url: str | None = None
    authority: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=128)
    board_or_exam: str | None = Field(default=None, max_length=255)
    academic_year: str | None = Field(default=None, max_length=64)
    effective_date: date | None = None
    copyright_classification: str | None = Field(default=None, max_length=128)
    trust_tier: SourceTrustTier
    anythingllm_workspace: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ManualSourceRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any]
    note: str | None = Field(default=None, max_length=2000)


class SourceRevisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_id: UUID
    revision_number: int = Field(ge=1)
    ingestion_method: SourceIngestionMethod
    checksum: str
    content_type: str
    byte_size: int = Field(ge=0)
    status: SourceRevisionStatus


class SourceValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list)


class SourceDiffSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_revision_id: UUID | None
    to_revision_id: UUID
    checksum_changed: bool
    metadata_changes: dict[str, Any] = Field(default_factory=dict)
    additions: int = Field(ge=0)
    removals: int = Field(ge=0)
    similarity: float = Field(ge=0, le=1)


class SourceProvenanceLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: UUID
    curriculum_version_id: UUID | None = None
    exam_version_id: UUID | None = None
    question_id: UUID | None = None
    policy_rule_id: UUID | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> SourceProvenanceLinkInput:
        target_ids = (
            self.curriculum_version_id,
            self.exam_version_id,
            self.question_id,
            self.policy_rule_id,
        )
        if sum(value is not None for value in target_ids) != 1:
            raise ValueError("exactly one provenance target must be supplied")
        return self
