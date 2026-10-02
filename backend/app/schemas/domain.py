from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    BlueprintRuleType,
    CognitiveLevel,
    CurriculumNodeType,
    DiagnosticCategory,
    PaperMode,
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
    retrieved_at: datetime | None = None
    checksum: str | None = None
    copyright_classification: str | None = None
    trust_tier: SourceTrustTier = SourceTrustTier.ANALYTICAL
    anythingllm_workspace: str | None = None
    status: SourceStatus = SourceStatus.STAGED
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OrganizationInput(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InstitutionInput(BaseModel):
    organization_id: UUID
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ActorInput(BaseModel):
    institution_id: UUID | None = None
    organization_id: UUID | None = None
    external_code: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumPackInput(BaseModel):
    framework_id: UUID | None = None
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    authority: str | None = None
    country: str = Field(min_length=2, max_length=128)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumVersionInput(BaseModel):
    curriculum_pack_id: UUID
    version_code: str = Field(min_length=1, max_length=64)
    academic_year: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_effective_window(self) -> CurriculumVersionInput:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("effective_from cannot be after effective_to")
        return self


class CurriculumNodeInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    curriculum_version_id: UUID
    parent_id: UUID | None = None
    node_type: CurriculumNodeType
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    sequence: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CurriculumHierarchyInput(BaseModel):
    nodes: list[CurriculumNodeInput]

    @model_validator(mode="after")
    def validate_hierarchy(self) -> CurriculumHierarchyInput:
        by_id = {node.id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("curriculum node ids must be unique")

        for node in self.nodes:
            if node.parent_id is None:
                continue
            if node.parent_id == node.id:
                raise ValueError("a curriculum node cannot be its own parent")
            parent = by_id.get(node.parent_id)
            if parent is None:
                raise ValueError("curriculum parent_id must reference a node in the hierarchy")
            if parent.curriculum_version_id != node.curriculum_version_id:
                raise ValueError("curriculum parent must belong to the same curriculum version")

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(node_id: UUID) -> None:
            if node_id in visiting:
                raise ValueError("curriculum hierarchy cannot contain cycles")
            if node_id in visited:
                return
            visiting.add(node_id)
            parent_id = by_id[node_id].parent_id
            if parent_id is not None:
                visit(parent_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in by_id:
            visit(node_id)
        return self


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


class ConceptPrerequisiteGraphInput(BaseModel):
    concept_ids: set[UUID]
    edges: list[ConceptPrerequisiteInput]

    @model_validator(mode="after")
    def validate_graph(self) -> ConceptPrerequisiteGraphInput:
        seen: set[tuple[UUID, UUID]] = set()
        adjacency: dict[UUID, set[UUID]] = {concept_id: set() for concept_id in self.concept_ids}
        for edge in self.edges:
            pair = (edge.prerequisite_concept_id, edge.target_concept_id)
            if pair in seen:
                raise ValueError("duplicate prerequisite edge")
            seen.add(pair)
            if edge.prerequisite_concept_id not in self.concept_ids:
                raise ValueError("prerequisite concept is missing from concept_ids")
            if edge.target_concept_id not in self.concept_ids:
                raise ValueError("target concept is missing from concept_ids")
            adjacency[edge.prerequisite_concept_id].add(edge.target_concept_id)

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(concept_id: UUID) -> None:
            if concept_id in visiting:
                raise ValueError("prerequisite graph cannot contain cycles")
            if concept_id in visited:
                return
            visiting.add(concept_id)
            for target_id in adjacency[concept_id]:
                visit(target_id)
            visiting.remove(concept_id)
            visited.add(concept_id)

        for concept_id in self.concept_ids:
            visit(concept_id)
        return self


class ExamPackInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    authority: str | None = None
    country: str = Field(min_length=2, max_length=128)
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExamVersionInput(BaseModel):
    exam_pack_id: UUID
    version_code: str = Field(min_length=1, max_length=64)
    academic_year: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    total_marks: float | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_effective_window(self) -> ExamVersionInput:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("effective_from cannot be after effective_to")
        return self


class ExamSectionInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    exam_version_id: UUID
    parent_section_id: UUID | None = None
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    sequence: int = 0
    subject_code: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)


class ExamStructureInput(BaseModel):
    sections: list[ExamSectionInput]

    @model_validator(mode="after")
    def validate_structure(self) -> ExamStructureInput:
        by_id = {section.id: section for section in self.sections}
        if len(by_id) != len(self.sections):
            raise ValueError("exam section ids must be unique")

        for section in self.sections:
            if section.parent_section_id is None:
                continue
            if section.parent_section_id == section.id:
                raise ValueError("an exam section cannot be its own parent")
            parent = by_id.get(section.parent_section_id)
            if parent is None:
                raise ValueError("exam parent_section_id must reference a section in the structure")
            if parent.exam_version_id != section.exam_version_id:
                raise ValueError("exam parent section must belong to the same exam version")

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(section_id: UUID) -> None:
            if section_id in visiting:
                raise ValueError("exam section structure cannot contain cycles")
            if section_id in visited:
                return
            visiting.add(section_id)
            parent_id = by_id[section_id].parent_section_id
            if parent_id is not None:
                visit(parent_id)
            visiting.remove(section_id)
            visited.add(section_id)

        for section_id in by_id:
            visit(section_id)
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
    id: UUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    category: DiagnosticCategory
    parent_id: UUID | None = None
    description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RubricCriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    max_marks: float = Field(gt=0)
    scoring_guidance: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RubricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterionInput] = Field(default_factory=list)
    total_marks: float | None = Field(default=None, gt=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rubric(self) -> RubricInput:
        codes = [criterion.code for criterion in self.criteria]
        if len(codes) != len(set(codes)):
            raise ValueError("rubric criterion codes must be unique")
        if self.total_marks is not None and self.criteria:
            criterion_total = sum(criterion.max_marks for criterion in self.criteria)
            if abs(criterion_total - self.total_marks) > 1e-9:
                raise ValueError("rubric total_marks must equal the sum of criterion max_marks")
        return self


class DistributionTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    weight: float = Field(ge=0, le=1)


class PaperSectionBlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    title: str | None = None
    exact_count: int | None = Field(default=None, ge=0)
    min_count: int | None = Field(default=None, ge=0)
    max_count: int | None = Field(default=None, ge=0)
    question_type_counts: dict[str, int] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_counts(self) -> PaperSectionBlueprintInput:
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError("section min_count cannot exceed max_count")
        if self.exact_count is not None:
            if self.min_count is not None and self.exact_count < self.min_count:
                raise ValueError("section exact_count contradicts min_count")
            if self.max_count is not None and self.exact_count > self.max_count:
                raise ValueError("section exact_count contradicts max_count")
        if any(count < 0 for count in self.question_type_counts.values()):
            raise ValueError("section question_type_counts cannot contain negative values")
        if self.exact_count is not None and self.question_type_counts:
            if sum(self.question_type_counts.values()) != self.exact_count:
                raise ValueError("section question_type_counts must sum to exact_count")
        return self


class PaperBlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: PaperMode
    total_question_count: int | None = Field(default=None, ge=1)
    sections: list[PaperSectionBlueprintInput] = Field(default_factory=list)
    topic_distribution: list[DistributionTargetInput] = Field(default_factory=list)
    difficulty_distribution: list[DistributionTargetInput] = Field(default_factory=list)
    cognitive_distribution: list[DistributionTargetInput] = Field(default_factory=list)
    competency_distribution: list[DistributionTargetInput] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def _validate_distribution(
        name: str,
        distribution: list[DistributionTargetInput],
    ) -> None:
        keys = [target.key for target in distribution]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{name} keys must be unique")
        if distribution:
            total = sum(target.weight for target in distribution)
            if abs(total - 1.0) > 1e-9:
                raise ValueError(f"{name} weights must sum to 1")

    @model_validator(mode="after")
    def validate_blueprint(self) -> PaperBlueprintInput:
        section_codes = [section.code for section in self.sections]
        if len(section_codes) != len(set(section_codes)):
            raise ValueError("paper section codes must be unique")
        if self.total_question_count is not None and self.sections:
            fixed_counts = [section.exact_count for section in self.sections]
            if all(count is not None for count in fixed_counts):
                fixed_total = sum(count for count in fixed_counts if count is not None)
                if fixed_total != self.total_question_count:
                    raise ValueError("fixed section counts must sum to total_question_count")
        self._validate_distribution("topic_distribution", self.topic_distribution)
        self._validate_distribution("difficulty_distribution", self.difficulty_distribution)
        self._validate_distribution("cognitive_distribution", self.cognitive_distribution)
        self._validate_distribution("competency_distribution", self.competency_distribution)
        return self


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
    model_config = ConfigDict(extra="forbid")

    external_code: str | None = Field(default=None, max_length=128)
    content_version: int = Field(default=1, ge=1)
    origin_type: QuestionOrigin
    curriculum_version_id: UUID | None = None
    exam_version_id: UUID | None = None
    primary_curriculum_node_id: UUID | None = None
    competency_ids: list[UUID] = Field(default_factory=list)
    learning_outcome_ids: list[UUID] = Field(default_factory=list)
    prerequisite_concept_ids: list[UUID] = Field(default_factory=list)
    source_ids: list[UUID] = Field(default_factory=list)
    question_type: QuestionType
    stem_text: str = Field(min_length=1)
    stem_latex: str | None = None
    solution_text: str | None = None
    solution_latex: str | None = None
    answer_json: dict[str, Any] = Field(default_factory=dict)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    cognitive_level: CognitiveLevel | None = None
    age_min: int | None = Field(default=None, ge=0)
    age_max: int | None = Field(default=None, ge=0)
    grade_year_codes: list[str] = Field(default_factory=list)
    rubric_json: RubricInput | None = None
    status: QuestionStatus = QuestionStatus.DRAFT
    options: list[QuestionOptionInput] = Field(default_factory=list)
    assets: list[QuestionAssetInput] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_question(self) -> QuestionInput:
        keys = [option.option_key for option in self.options]
        if len(keys) != len(set(keys)):
            raise ValueError("question option keys must be unique")
        correct = sum(option.is_correct for option in self.options)
        if self.question_type is QuestionType.SINGLE_CHOICE and correct != 1:
            raise ValueError("single-choice questions require exactly one correct option")
        if self.question_type is QuestionType.MULTIPLE_CHOICE and correct < 1:
            raise ValueError("multiple-choice questions require at least one correct option")
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("age_min cannot exceed age_max")
        if len(self.grade_year_codes) != len(set(self.grade_year_codes)):
            raise ValueError("grade_year_codes must be unique")
        for name, values in (
            ("competency_ids", self.competency_ids),
            ("learning_outcome_ids", self.learning_outcome_ids),
            ("prerequisite_concept_ids", self.prerequisite_concept_ids),
            ("source_ids", self.source_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique identifiers")
        return self


class TestDefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    curriculum_version_id: UUID | None = None
    exam_version_id: UUID | None = None
    blueprint_json: PaperBlueprintInput
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

    @model_validator(mode="after")
    def validate_effective_window(self) -> PolicyRuleInput:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("effective_from cannot be after effective_to")
        return self


class DomainModelInfo(BaseModel):
    version: str = "d02"
    curriculum_node_types: list[str]
    question_types: list[str]
    source_types: list[str]
    diagnostic_categories: list[str]
