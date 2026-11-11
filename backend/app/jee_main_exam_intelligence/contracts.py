from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSectionCode,
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)


class PaperPlanSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    subject_code: JeeMainSubjectCode
    section_code: JeeMainSectionCode | None = None
    question_type: JeeMainQuestionTypeQuota | None = None
    topic_code: str | None = None
    derived_topic_group: str | None = None
    marks: float | None = None
    negative_marks: float | None = None
    question_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PaperPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    exam_pack_code: str = "jee-main"
    exam_version_code: str
    mode: PaperPlanMode
    organization_id: str | None = None
    institution_id: str | None = None
    subject_code: JeeMainSubjectCode | None = None
    topic_code: str | None = None
    derived_topic_group: str | None = None
    requested_count: int | None = Field(default=None, ge=1)
    allowed_source_revision_ids: list[str] = Field(default_factory=list)
    require_official_pattern_verified: bool = False
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION
    idempotency_key: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PaperPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    verdict: PaperPlanVerdict
    mode: PaperPlanMode
    exam_version_code: str
    requested_count: int
    actual_count: int
    slots: list[PaperPlanSlot] = Field(default_factory=list)
    issue_codes: list[PaperPlanIssueCode] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)
    plan_checksum: str
    official_pattern_label: str | None = None
    source_revision_refs: list[str] = Field(default_factory=list)
    scoring_preview: dict[str, Any] = Field(default_factory=dict)
    test_definition_id: str | None = None
    test_definition_code: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OfficialSourceRegistrationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str
    revision_id: str | None
    candidate_url: str
    revision_status: str
    checksum_sha256: str | None
    verified_for_official_pattern: bool
