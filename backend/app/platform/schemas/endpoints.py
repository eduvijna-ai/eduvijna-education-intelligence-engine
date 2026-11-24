from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.platform.schemas.common import StrictModel


class KnowledgeSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    curriculum_version_id: UUID | None = None


class KnowledgeSearchHit(StrictModel):
    snippet: str
    source_ref: str
    provenance: dict[str, str] = Field(default_factory=dict)


class KnowledgeSearchResponse(StrictModel):
    hits: list[KnowledgeSearchHit]
    query: str


class GenerateQuestionsRequest(StrictModel):
    topic_code: str = Field(min_length=1, max_length=128)
    count: int = Field(ge=1, le=50)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ValidateQuestionRequest(StrictModel):
    question_text: str = Field(min_length=1, max_length=8000)
    curriculum_node_id: UUID | None = None


class ValidateQuestionResponse(StrictModel):
    verdict: str
    diagnostic_only: bool = True
    notes: str


class GenerateMockExamRequest(StrictModel):
    exam_version_id: UUID
    question_count: int = Field(ge=1, le=200)
    idempotency_key: str = Field(min_length=8, max_length=128)


class AttemptSubmitRequest(StrictModel):
    learner_id: UUID
    responses: list[dict[str, str]] = Field(default_factory=list)


class RemediationRequest(StrictModel):
    diagnostic_ref: str = Field(min_length=1, max_length=128)


class AdminSourceUpsertRequest(StrictModel):
    source_code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    lifecycle: str = Field(default="registered")


class CurriculumListItem(StrictModel):
    id: UUID
    code: str
    title: str


class ExamListItem(StrictModel):
    id: UUID
    code: str
    title: str
