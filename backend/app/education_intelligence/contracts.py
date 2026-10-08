from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.education_intelligence.enums import (
    EvidenceAuthority,
    ValidationSeverity,
    ValidationStatus,
)


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: EvidenceAuthority
    entity_type: str
    entity_id: str | None = None
    source_revision_id: str | None = None
    locator: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class CognitiveDemandEvidence(BaseModel):
    """Structured cognitive-demand signals (D6-09); labels alone are insufficient."""

    model_config = ConfigDict(extra="forbid")

    recall_required: bool = False
    interpretation_required: bool = False
    application_required: bool = False
    multi_step_reasoning: bool = False
    comparison_or_evaluation: bool = False
    justification_required: bool = False
    notes: str | None = None


class DifficultyEvidence(BaseModel):
    """Design-time difficulty profile (D6-12); not learner-calibrated."""

    model_config = ConfigDict(extra="forbid")

    cognitive_demand_band: int | None = Field(default=None, ge=1, le=5)
    prerequisite_depth: int | None = Field(default=None, ge=0)
    step_count: int | None = Field(default=None, ge=0)
    abstraction_level: int | None = Field(default=None, ge=1, le=5)
    computation_load: int | None = Field(default=None, ge=1, le=5)
    language_load: int | None = Field(default=None, ge=1, le=5)
    expected_effort_minutes: float | None = Field(default=None, ge=0)


class QuestionOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    text: str
    is_correct: bool = False


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    title: str
    marks: float
    weight: float | None = None
    performance_levels: list[dict[str, Any]] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)


class CanonicalRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterion] = Field(default_factory=list)
    total_marks: float | None = None


class CanonicalAssessmentItem(BaseModel):
    """Versioned canonical item input for Day 6 validation (no generation)."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    stem_text: str
    question_type: str = "single_choice"
    options: list[QuestionOptionInput] = Field(default_factory=list)
    declared_cognitive_level: str | None = None
    competency_codes: list[str] = Field(default_factory=list)
    competency_claim_official: bool = False
    learning_outcome_ids: list[str] = Field(default_factory=list)
    curriculum_version_id: str | None = None
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    declared_difficulty: int | None = Field(default=None, ge=1, le=5)
    difficulty_evidence: DifficultyEvidence | None = None
    cognitive_demand_evidence: CognitiveDemandEvidence | None = None
    cognitive_progression: list[str] = Field(default_factory=list)
    age_min: int | None = None
    age_max: int | None = None
    language_complexity_flag: str | None = None
    sensitive_context: bool = False
    rubric: CanonicalRubric | None = None
    answer_metadata_present: bool = True
    explanation_required: bool = False
    explanation_present: bool = False
    notation_asset_refs_valid: bool = True
    institution_id: str | None = None
    content_text_for_safety: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    def canonical_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validator_id: str
    validator_version: str
    status: ValidationStatus
    rule_codes: list[str] = Field(default_factory=list)
    severity: ValidationSeverity = ValidationSeverity.ADVISORY
    blocking: bool = False
    target: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    taxonomy_version: str | None = None
    policy_version: str | None = None
    source_entity_refs: list[dict[str, str]] = Field(default_factory=list)
    input_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_summary: str | None = None


class ValidationRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    input_hash: str
    aggregate_status: ValidationStatus
    blocking_failure: bool
    results: list[ValidationResult]
    taxonomy_version: str
    policy_version: str
    validator_versions: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    explanations: list[str] = Field(default_factory=list)


class InstitutionPolicyOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution_id: str
    policy_key: str
    value: dict[str, Any] = Field(default_factory=dict)
    tightens_only: bool = True


class PolicyRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_key: str
    authority_tier: str
    scope_code: str
    value: dict[str, Any] = Field(default_factory=dict)
    severity: ValidationSeverity = ValidationSeverity.MANDATORY
    blocking: bool = True
    rule_code: str
    source_revision_id: str | None = None
    prohibits: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)


class CognitiveProgressionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    progression_id: str
    ordered_levels: list[str]


def infer_observed_cognitive_level(evidence: CognitiveDemandEvidence) -> tuple[str | None, bool]:
    """Map demand evidence to v1 cognitive level; uncertain => review."""
    if evidence.justification_required or evidence.comparison_or_evaluation:
        return "evaluate", False
    if evidence.multi_step_reasoning:
        return "analyze", False
    if evidence.application_required:
        return "apply", False
    if evidence.interpretation_required:
        return "understand", False
    if evidence.recall_required:
        return "remember", False
    return None, True
