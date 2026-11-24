from __future__ import annotations

from pydantic import BaseModel, Field

from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    IssueCode,
    PlanVerdict,
)


class QuestionRef(BaseModel):
    question_id: str
    paper_or_section: str
    topic_code: str | None = None
    fingerprint: str
    correct_key: str | None = None
    marks_if_correct: float
    marks_if_incorrect: float
    stem_text: str | None = None
    options: dict[str, str] | None = None
    question_kind: str = "objective"
    rubric_criteria: list[dict[str, object]] | None = None
    independently_validated: bool = False


class DescriptiveSubpart(BaseModel):
    subpart_id: str
    prompt: str
    max_marks: float
    model_solution_steps: list[str]
    partial_credit_bounds: tuple[float, float]


class DescriptiveItemContract(BaseModel):
    """D14-11: multipart descriptive stem with rubric; no auto subjective grading claim."""

    item_id: str
    paper_code: str
    stem_intro: str
    subparts: list[DescriptiveSubpart]
    total_marks: float
    rubric_valid: bool
    automated_grading_claimed: bool = False


class AllocateRequest(BaseModel):
    exam_pack_code: str
    profile_kind: Day14ProfileKind
    trust_mode: Day14SourceTrustMode
    paper_or_section: str
    requested_count: int = 10
    session_code: str = "jan2027"
    academic_year: str = "2026"
    stream: EapcetStream | None = None
    topic_code: str | None = None
    organization_id: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class AllocateResult(BaseModel):
    verdict: PlanVerdict
    requested_count: int
    delivered_count: int
    questions: list[QuestionRef]
    issue_codes: list[IssueCode]
    checksum: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class CaPaperPlanRequest(BaseModel):
    exam_pack_code: str = CA_FOUNDATION_PACK_CODE
    profile_kind: Day14ProfileKind
    trust_mode: Day14SourceTrustMode
    session_code: str = "jan2027"
    papers: list[str] | None = None
    items_per_paper: int | None = None


class CaPaperPlanResult(BaseModel):
    verdict: PlanVerdict
    papers: dict[str, AllocateResult]
    total_marks: int
    issue_codes: list[IssueCode]
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ImatPaperPlanRequest(BaseModel):
    exam_pack_code: str
    profile_kind: Day14ProfileKind
    trust_mode: Day14SourceTrustMode
    academic_year: str
    requested_count: int | None = None


class ImatPaperPlanResult(BaseModel):
    verdict: PlanVerdict
    total_questions: int
    delivered_count: int
    sections: dict[str, int]
    decimal_total_marks: float
    issue_codes: list[IssueCode]
    metadata_json: dict[str, object] = Field(default_factory=dict)


class EapcetPaperPlanRequest(BaseModel):
    exam_pack_code: str
    profile_kind: Day14ProfileKind
    trust_mode: Day14SourceTrustMode
    stream: EapcetStream
    exam_year: str = "2026"
    requested_count: int | None = None
    medium_pair: str = "english_telugu"


class EapcetPaperPlanResult(BaseModel):
    verdict: PlanVerdict
    stream: EapcetStream
    total_questions: int
    delivered_count: int
    section_counts: dict[str, int]
    duration_minutes: int
    issue_codes: list[IssueCode]
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ExtensibilityProof(BaseModel):
    """D14-26: evidence that generic modules were not EAPCET-branched."""

    generic_modules_inspected: list[str]
    eapcet_specific_branches_in_generic: list[str]
    pack_config_driven: bool
    verdict: PlanVerdict