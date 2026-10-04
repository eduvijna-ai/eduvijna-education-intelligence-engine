"""Internal typed framework contracts; no board-specific levels or API routes."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.curriculum_intelligence import AlignmentStatus

FrameworkLevel = Literal["stage", "curricular_area", "goal", "competency"]
PublicationStatus = Literal["draft", "final"]
ReviewStatus = Literal["review_required", "reviewed"]


class FrameworkNodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    level: FrameworkLevel
    code: str = Field(min_length=1, max_length=128)
    official_code: str | None = Field(default=None, min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    official_text: str | None = None
    parent_code: str | None = Field(default=None, min_length=1, max_length=128)
    competency_id: UUID | None = None
    sequence: int = 0
    source_locator: str = Field(min_length=1, max_length=1024)
    publication_status: PublicationStatus
    review_status: ReviewStatus = "review_required"
    inferred: bool = False

    @model_validator(mode="after")
    def valid_leaf(self) -> FrameworkNodeSpec:
        if (self.level == "competency") != (self.competency_id is not None):
            raise ValueError("only competency-level nodes require competency_id")
        return self


class LearningOutcomeCompetencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    curriculum_version_id: UUID
    learning_outcome_id: UUID
    competency_node_id: UUID
    relationship_type: str = Field(default="supports", min_length=1, max_length=64)
    status: AlignmentStatus = "review_required"
    inferred: bool = True
    publication_status: PublicationStatus
    review_status: ReviewStatus = "review_required"
    source_revision_id: UUID
    source_locator: str = Field(min_length=1, max_length=1024)
    evidence_text: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def valid_assertion(self) -> LearningOutcomeCompetencyInput:
        if self.status == "direct":
            if self.inferred or self.review_status != "reviewed" or not self.evidence_text:
                raise ValueError("direct links require reviewed, non-inferred source evidence")
        else:
            self.inferred = True
        return self


class FrameworkNodeResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    framework_id: UUID
    level: FrameworkLevel
    code: str
    official_code: str | None
    title: str
    official_text: str | None
    parent_id: UUID | None
    competency_id: UUID | None
    source_revision_id: UUID
    source_locator: str
    publication_status: PublicationStatus
    review_status: ReviewStatus
    inferred: bool


class LearningOutcomeCompetencyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    curriculum_version_id: UUID
    learning_outcome_id: UUID
    competency_node_id: UUID
    relationship_type: str
    status: AlignmentStatus
    inferred: bool
    publication_status: PublicationStatus
    review_status: ReviewStatus
    source_revision_id: UUID
    source_locator: str
    evidence_text: str | None


class FrameworkPathResult(BaseModel):
    framework_id: UUID
    framework_version_code: str
    nodes: list[FrameworkNodeResult]
    learning_outcome_links: list[LearningOutcomeCompetencyResult] = Field(default_factory=list)
