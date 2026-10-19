from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.orchestration.enums import (
    HARD_MAX_REPAIRS,
    OrchestrationRunStatus,
    ReviewVerdictStatus,
)


class QuestionOptionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    text: str
    is_correct: bool = False


class DraftQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    slot_index: int
    stem_text: str
    question_type: str = "single_choice"
    options: list[QuestionOptionDraft] = Field(default_factory=list)
    marks: float | None = None
    source_revision_ids: list[str] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)
    declared_cognitive_level: str | None = None
    declared_difficulty: int | None = Field(default=None, ge=1, le=5)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    def content_fingerprint(self) -> str:
        payload = {
            "stem": re.sub(r"\s+", " ", self.stem_text.strip().lower()),
            "options": sorted(
                (o.option_key, re.sub(r"\s+", " ", o.text.strip().lower())) for o in self.options
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SolverResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    proposed_answer_key: str | None = None
    working_summary: str | None = None
    check_status: str = "unknown"
    agrees_with_author: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str
    item_id: str
    status: ReviewVerdictStatus
    issue_codes: list[str] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ResolvedScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_version_id: str | None = None
    exam_version_id: str | None = None
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    actor_id: str | None = None
    scope_warnings: list[str] = Field(default_factory=list)
    scope_errors: list[str] = Field(default_factory=list)


class GenerationPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    slot_index: int


class GenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GenerationPlanItem]
    requested_count: int


class DeterministicValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    blocking: bool
    repairable: bool
    review_required: bool
    issue_codes: list[str] = Field(default_factory=list)


class DuplicateValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    is_duplicate: bool
    duplicate_of_item_id: str | None = None
    issue_codes: list[str] = Field(default_factory=list)


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str = Field(min_length=8, max_length=128)
    generation_mode: str = "generic_batch"
    requested_count: int = Field(default=1, ge=1, le=20)
    curriculum_version_id: str | None = None
    exam_version_id: str | None = None
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    question_type: str = "single_choice"
    marks: float | None = Field(default=None, gt=0)
    difficulty_target: int | None = Field(default=None, ge=1, le=5)
    cognitive_target: str | None = None
    competency_target: str | None = None
    retrieval_profile_version: str = Field(min_length=1, max_length=64)
    retrieval_query: str | None = None
    max_repairs: int = Field(default=2, ge=0, le=HARD_MAX_REPAIRS)
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    actor_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic_codes", "concept_codes")
    @classmethod
    def _strip_codes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    def request_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"run_id"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def fixture_scenario(self) -> str:
        value = self.metadata_json.get("fixture_scenario")
        return str(value) if value else "clean_pass"

    def diagnostic_enrichment_enabled(self) -> bool:
        return bool(self.metadata_json.get("diagnostic_enrichment_enabled"))

    def diagnostic_fixture_scenario(self) -> str:
        value = self.metadata_json.get("diagnostic_fixture_scenario")
        return str(value) if value else "diagnostic_clean_pass"

    def effective_max_repairs(self) -> int:
        return min(self.max_repairs, HARD_MAX_REPAIRS)


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: OrchestrationRunStatus
    requested_count: int
    approved_count: int
    items: list[DraftQuestionItem] = Field(default_factory=list)
    source_revision_ids: list[str] = Field(default_factory=list)
    retrieval_profile_version: str
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    repair_summary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_refs: list[str] = Field(default_factory=list)
    request_hash: str
    started_at: datetime
    completed_at: datetime | None = None
    gateway_usage: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


def new_run_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)
