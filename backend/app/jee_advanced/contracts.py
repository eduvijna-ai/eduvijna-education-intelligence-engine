from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)


class PracticeQuestionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    subject_code: str
    topic_group: str | None = None
    independently_validated: bool = False
    solver_audit_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SubjectPracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_pack_code: str
    profile_kind: AdvancedProfileKind
    trust_mode: JeeAdvancedSourceTrustMode
    subject_code: str
    requested_count: int = Field(ge=1, le=200)
    organization_id: str | None = None
    idempotency_key: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SubjectPracticeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: AdvancedPlanVerdict
    subject_code: str
    requested_count: int
    delivered_count: int
    questions: list[PracticeQuestionRef]
    issue_codes: list[AdvancedIssueCode] = Field(default_factory=list)
    trust_mode: JeeAdvancedSourceTrustMode
    result_fingerprint: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TopicPracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_pack_code: str
    profile_kind: AdvancedProfileKind
    trust_mode: JeeAdvancedSourceTrustMode
    subject_code: str
    topic_group: str
    requested_count: int = Field(ge=1, le=200)
    organization_id: str | None = None
    idempotency_key: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TopicPracticeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: AdvancedPlanVerdict
    subject_code: str
    topic_group: str
    requested_count: int
    delivered_count: int
    questions: list[PracticeQuestionRef]
    issue_codes: list[AdvancedIssueCode] = Field(default_factory=list)
    trust_mode: JeeAdvancedSourceTrustMode
    result_fingerprint: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AdvancedPaperPlanRequest(BaseModel):
    """D12-17 typed planner envelope."""

    model_config = ConfigDict(extra="forbid")

    exam_pack_code: str
    profile_kind: AdvancedProfileKind
    trust_mode: JeeAdvancedSourceTrustMode
    academic_year: str
    paper_codes: list[str] = Field(default_factory=list)
    simulate_full_pair: bool = False
    subject_filters: list[str] = Field(default_factory=list)
    topic_filters: list[str] = Field(default_factory=list)
    requested_counts: dict[str, int] = Field(default_factory=dict)
    organization_id: str | None = None
    source_revision_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    rights_scope: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AdvancedPaperPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: AdvancedPlanVerdict
    exam_pack_code: str
    profile_kind: AdvancedProfileKind
    trust_mode: JeeAdvancedSourceTrustMode
    academic_year: str
    paper_codes: list[str]
    issue_codes: list[AdvancedIssueCode] = Field(default_factory=list)
    paper_checksums: dict[str, str] = Field(default_factory=dict)
    origin_audit: dict[str, Any] = Field(default_factory=dict)
    result_fingerprint: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
