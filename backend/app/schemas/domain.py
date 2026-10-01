from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    BlueprintRuleType,
    CognitiveLevel,
    CurriculumNodeType,
    DiagnosticCategory,
    PolicyScopeType,
    QuestionAssetType,
    QuestionOrigin,
    QuestionStatus,
    QuestionType,
    SourceStatus,
    SourceTrustTier,
    SourceType,
    TestStatus,
)


class SourceInput(BaseModel):
    source_type: SourceType
    title: str = Field(min_length=1, max_length=512)
    url: str | None = None
    authority: str | None = None
    country: str | None = None
    board_or_exam: str | None = None
    academic_year: str | None = None
    effective_date: date | None = None
    checksum: str | None = None
    trust_tier: SourceTrustTier = SourceTrustTier.ANALYTICAL
    status: SourceStatus = SourceStatus.STAGED
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumNodeInput(BaseModel):
    curriculum_version_id: UUID
    parent_id: UUID | None = None
    node_type: CurriculumNodeType
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    sequence: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConceptPrerequisiteInput(BaseModel):
    prerequisite_concept_id: UUID
    target_concept_id: UUID
    relation_type: str = "prerequisite"
    weight: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def reject_self_reference(self) -> ConceptPrerequisiteInput:
        if self.prerequisite_concept_id == self.target_concept_id:
            raise ValueError("a concept cannot be its own prerequisite")
        return self


class ExamBlueprintRuleInput(BaseModel):
    rule_type: BlueprintRuleType
    selector_json: dict[str, Any] = Field(default_factory=dict)
    exact_count: int | None = Field(default=None, ge=0)
    min_count: int | None = Field(default=None, ge=0)
    max_count: int | None = Field(default=None, ge=0)
    marks_per_question: float | None = None
    negative_marks: float | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> ExamBlueprintRuleInput:
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError("min_count cannot exceed max_count")
        if self.exact_count is not None:
            if self.min_count is not None and self.exact_count < self.min_count:
                raise ValueError("exact_count contradicts min_count")
            if self.max_count is not None and self.exact_count > self.max_count:
                raise ValueError("exact_count contradicts max_count")
        return self


class DiagnosticTaxonomyInput(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    category: DiagnosticCategory
    parent_id: UUID | None = None
    description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QuestionOptionInput(BaseModel):
    option_key: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1)
    latex: str | None = None
    is_correct: bool = False
    diagnostic_taxonomy_entry_id: UUID | None = None
    error_code: str | None = None
    sequence: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QuestionAssetInput(BaseModel):
    asset_type: QuestionAssetType
    uri: str | None = None
    alt_text: str | None = None
    payload_json: dict[str, Any] | None = None
    sequence: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QuestionInput(BaseModel):
    origin_type: QuestionOrigin
    question_type: QuestionType
    stem_text: str = Field(min_length=1)
    stem_latex: str | None = None
    solution_text: str | None = None
    solution_latex: str | None = None
    answer_json: dict[str, Any] = Field(default_factory=dict)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    cognitive_level: CognitiveLevel | None = None
    status: QuestionStatus = QuestionStatus.DRAFT
    options: list[QuestionOptionInput] = Field(default_factory=list)
    assets: list[QuestionAssetInput] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_options(self) -> QuestionInput:
        keys = [option.option_key for option in self.options]
        if len(keys) != len(set(keys)):
            raise ValueError("question option keys must be unique")
        correct = sum(option.is_correct for option in self.options)
        if self.question_type is QuestionType.SINGLE_CHOICE and correct != 1:
            raise ValueError("single-choice questions require exactly one correct option")
        if self.question_type is QuestionType.MULTIPLE_CHOICE and correct < 1:
            raise ValueError("multiple-choice questions require at least one correct option")
        return self


class TestDefinitionInput(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    curriculum_version_id: UUID | None = None
    exam_version_id: UUID | None = None
    blueprint_json: dict[str, Any] = Field(default_factory=dict)
    status: TestStatus = TestStatus.DRAFT
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PolicyRuleInput(BaseModel):
    scope_type: PolicyScopeType
    scope_code: str = Field(min_length=1, max_length=128)
    policy_key: str = Field(min_length=1, max_length=255)
    value_json: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    active: bool = True
    effective_from: date | None = None
    effective_to: date | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DomainModelInfo(BaseModel):
    version: str = "d02"
    curriculum_node_types: list[str]
    question_types: list[str]
    source_types: list[str]
    diagnostic_categories: list[str]
