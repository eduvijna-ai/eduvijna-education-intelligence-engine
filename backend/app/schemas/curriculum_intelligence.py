from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CurriculumNodeType, SourceTrustTier, SourceType
from app.schemas.assessment_pattern import AssessmentPattern

AlignmentStatus = Literal["direct", "partial", "unresolved", "review_required"]


class OfficialSourceManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=512)
    url: str
    authority: str = Field(min_length=1, max_length=255)
    country: str = Field(default="India", min_length=2, max_length=128)
    board_or_exam: str | None = Field(default=None, max_length=255)
    academic_year: str | None = Field(default=None, max_length=64)
    document_type: str = Field(min_length=1, max_length=128)
    version_applicability: str | None = Field(default=None, max_length=255)
    checksum: str | None = Field(default=None, min_length=64, max_length=128)
    checksum_policy: str = Field(default="computed_on_ingestion", max_length=128)
    copyright_classification: str = Field(default="official_reference", max_length=128)
    trust_tier: SourceTrustTier = SourceTrustTier.OFFICIAL_PRIMARY
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumNodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: CurriculumNodeType
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    parent_code: str | None = Field(default=None, max_length=128)
    sequence: int = 0
    official_text: str | None = None
    source_locator: str | None = Field(default=None, max_length=1024)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class LearningOutcomeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)
    normalized_text: str | None = None
    source_locator: str | None = Field(default=None, max_length=1024)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompetencySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    official_text: str | None = None
    source_locator: str | None = Field(default=None, max_length=1024)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumAlignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_version_id: UUID
    curriculum_node_id: UUID
    learning_outcome_id: UUID | None = None
    competency_id: UUID | None = None
    relationship_type: str = Field(min_length=1, max_length=64)
    status: AlignmentStatus
    confidence: float | None = Field(default=None, ge=0, le=1)
    inferred: bool = False
    source_revision_id: UUID
    source_locator: str | None = Field(default=None, max_length=1024)
    evidence_text: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def exactly_one_target(self) -> CurriculumAlignmentInput:
        if (self.learning_outcome_id is None) == (self.competency_id is None):
            raise ValueError("exactly one of learning_outcome_id or competency_id is required")
        if self.status == "direct" and self.inferred:
            raise ValueError("direct alignments cannot be marked inferred")
        if self.status in {"unresolved", "review_required"} and not self.inferred:
            # Unresolved/review-required mappings are never official assertions.
            self.inferred = True
        return self


class AssessmentEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_version_id: UUID
    grade_node_id: UUID | None = None
    subject_node_id: UUID | None = None
    evidence_type: str = Field(min_length=1, max_length=64)
    source_revision_id: UUID
    source_locator: str | None = Field(default=None, max_length=1024)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_assessment_pattern(self) -> AssessmentEvidenceInput:
        if self.evidence_type == "assessment_pattern":
            self.evidence_json = AssessmentPattern.model_validate(self.evidence_json).model_dump()
        return self


class CoverageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_nodes: int = Field(ge=0)
    mapped_nodes: int = Field(ge=0)
    partial_nodes: int = Field(ge=0)
    unresolved_nodes: int = Field(ge=0)
    unmapped_nodes: int = Field(ge=0)

    @property
    def mapped_ratio(self) -> float:
        return 0.0 if self.total_nodes == 0 else self.mapped_nodes / self.total_nodes


class CurriculumPathResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework_id: UUID
    curriculum_pack_id: UUID
    curriculum_version_id: UUID
    node_ids: list[UUID]
    learning_outcome_ids: list[UUID] = Field(default_factory=list)
    competency_ids: list[UUID] = Field(default_factory=list)
    alignment_ids: list[UUID] = Field(default_factory=list)
    source_revision_ids: list[UUID] = Field(default_factory=list)
