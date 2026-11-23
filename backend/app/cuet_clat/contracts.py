from __future__ import annotations

from pydantic import BaseModel, Field

from app.cuet_clat.constants import MATHEMATICS_DOMAIN
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict


class PracticeQuestionRef(BaseModel):
    question_id: str
    subject_code: str
    topic_code: str | None = None
    passage_id: str | None = None
    fingerprint: str
    correct_key: str
    marks_if_correct: float
    marks_if_incorrect: float


class CuetPracticeRequest(BaseModel):
    exam_pack_code: str
    profile_kind: CuetClatProfileKind
    trust_mode: CuetClatSourceTrustMode
    test_subject_code: str = MATHEMATICS_DOMAIN
    requested_count: int = 10
    medium_code: str = "english"
    academic_year: str = "2026"
    organization_id: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class CuetPracticeResult(BaseModel):
    verdict: PlanVerdict
    requested_count: int
    delivered_count: int
    questions: list[PracticeQuestionRef]
    issue_codes: list[IssueCode]
    checksum: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class CuetSingleTestRequest(BaseModel):
    exam_pack_code: str
    profile_kind: CuetClatProfileKind
    trust_mode: CuetClatSourceTrustMode
    test_subject_code: str
    academic_year: str = "2026"
    medium_code: str = "english"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class CuetSingleTestResult(BaseModel):
    verdict: PlanVerdict
    question_count: int
    duration_minutes: int
    marks_correct: float
    marks_incorrect: float
    questions: list[PracticeQuestionRef]
    issue_codes: list[IssueCode]
    checksum: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ClatSectionAllocation(BaseModel):
    section_code: str
    question_count: int
    min_allowed: int
    max_allowed: int


class PassageCluster(BaseModel):
    passage_id: str
    passage_text: str
    section_code: str
    authorship: str
    source_snapshot_id: str | None = None
    fact_date: str | None = None
    question_ids: list[str]
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ClatPaperPlanRequest(BaseModel):
    exam_pack_code: str
    profile_kind: CuetClatProfileKind
    trust_mode: CuetClatSourceTrustMode
    academic_year: str = "2027"
    section_overrides: dict[str, int] | None = None
    replay_idempotency_key: str | None = None
    organization_id: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ClatPaperPlanResult(BaseModel):
    verdict: PlanVerdict
    total_questions: int
    duration_minutes: int
    section_allocations: list[ClatSectionAllocation]
    passage_clusters: list[PassageCluster]
    questions: list[PracticeQuestionRef]
    issue_codes: list[IssueCode]
    checksum: str
    metadata_json: dict[str, object] = Field(default_factory=dict)