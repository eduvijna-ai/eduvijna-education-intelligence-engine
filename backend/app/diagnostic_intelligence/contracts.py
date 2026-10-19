from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.diagnostic_intelligence.enums import (
    DEFAULT_TAXONOMY_VERSION,
    DiagnosticValidationStatus,
    MisconceptionStatus,
)
from app.diagnostic_intelligence.integration.revision_tenancy import RevisionTenantRecord

MAX_DIAGNOSTIC_BOUNDED_CHARS = 4000
MAX_DAY7_SNIPPET_CHARS = 512
MAX_DIAGNOSTIC_AGGREGATE_CHARS = 4000


class DiagnosticQuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    text: str
    is_correct: bool = False


class DiagnosticQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    stem_text: str
    question_type: str = "single_choice"
    options: list[DiagnosticQuestionOption] = Field(default_factory=list)
    source_revision_ids: list[str] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MisconceptionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    misconception_code: str
    version: str
    title: str
    description: str
    domain: str
    subject_code: str | None = None
    grade_year_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)
    error_pattern: str
    diagnostic_signal: str
    evidence_source_revision_ids: list[str] = Field(default_factory=list)
    status: MisconceptionStatus = MisconceptionStatus.ACTIVE
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MisconceptionTaxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    misconceptions: list[MisconceptionDefinition]


class OptionDiagnosticTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_key: str
    is_correct: bool
    misconception_code: str | None = None
    diagnostic_signal: str | None = None
    error_pattern: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION
    validation_status: DiagnosticValidationStatus = DiagnosticValidationStatus.PASS
    issue_codes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class Day7DiagnosticEvidenceSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_label: str = Field(max_length=256)
    source_revision_id: str = Field(max_length=128)
    snippet: str = Field(max_length=MAX_DAY7_SNIPPET_CHARS)


class DiagnosticCoverageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    distinct_misconception_codes: list[str] = Field(default_factory=list)
    duplicate_codes: list[str] = Field(default_factory=list)
    missing_distractor_tags: int = 0
    coverage_complete: bool = False
    warnings: list[str] = Field(default_factory=list)


class DiagnosticAuthoringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: DiagnosticQuestionItem
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION
    subject_code: str | None = None
    grade_year_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)
    curriculum_version_id: str | None = None
    exam_version_id: str | None = None
    medium_code: str | None = None
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    actor_id: str | None = None
    allowed_source_revision_ids: list[str] = Field(default_factory=list)
    allowed_evidence_refs: list[str] = Field(default_factory=list)
    blocked_tenant_revision_ids: list[str] = Field(default_factory=list)
    revision_tenant_records: dict[str, RevisionTenantRecord] = Field(default_factory=dict)
    coverage_policy: str = "distinct_misconceptions"
    fixture_scenario: str = "diagnostic_clean_pass"
    bounded_day7_context: str = Field(default="", max_length=MAX_DIAGNOSTIC_BOUNDED_CHARS)
    day7_evidence_snippets: list[Day7DiagnosticEvidenceSnippet] = Field(default_factory=list)

    @field_validator("day7_evidence_snippets")
    @classmethod
    def _snippet_aggregate_budget(
        cls, snippets: list[Day7DiagnosticEvidenceSnippet]
    ) -> list[Day7DiagnosticEvidenceSnippet]:
        total = sum(len(s.snippet) for s in snippets)
        if total > MAX_DIAGNOSTIC_AGGREGATE_CHARS:
            raise ValueError("diagnostic_evidence_budget_exceeded")
        return snippets


class DistractorDiagnosticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    question_type: str
    option_tags: list[OptionDiagnosticTag] = Field(default_factory=list)
    coverage_summary: DiagnosticCoverageSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION
    source_revision_ids: list[str] = Field(default_factory=list)
    audit_refs: list[str] = Field(default_factory=list)
    aggregate_status: DiagnosticValidationStatus = DiagnosticValidationStatus.PASS


class DiagnosticVerdictItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_key: str | None = None
    status: DiagnosticValidationStatus
    issue_codes: list[str] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)
    misconception_code: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)


class DiagnosticVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: DiagnosticValidationStatus
    items: list[DiagnosticVerdictItem] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)
    blocking: bool = False
    repairable: bool = False
    review_required: bool = False
