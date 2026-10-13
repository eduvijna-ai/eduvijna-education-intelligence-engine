from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class KnowledgeRetrievalRequest(BaseModel):
    query_text: str = Field(min_length=1, max_length=8000)
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    curriculum_version_id: str | None = None
    exam_version_id: str | None = None
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    source_authority_tiers: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=50)
    retrieval_profile_version: str = Field(min_length=1, max_length=64)
    actor_id: str | None = None

    @field_validator("topic_codes", "concept_codes", "source_authority_tiers")
    @classmethod
    def _strip_codes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class KnowledgeEvidenceItem(BaseModel):
    source_id: str
    source_revision_id: str
    source_revision_checksum: str
    binding_id: str
    trust_tier: str
    authority_label: str
    title: str
    locator: str
    snippet: str
    retrieval_score: float
    retrieval_rank: int
    anythingllm_workspace: str
    anythingllm_document_id: str
    entity_refs: dict[str, Any] = Field(default_factory=dict)
    citation_label: str


class AppliedKnowledgeScope(BaseModel):
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    curriculum_version_id: str | None = None
    exam_version_id: str | None = None
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    topic_codes: list[str] = Field(default_factory=list)
    concept_codes: list[str] = Field(default_factory=list)
    source_authority_tiers: list[str] = Field(default_factory=list)
    workspaces_queried: list[str] = Field(default_factory=list)


class KnowledgeRetrievalResult(BaseModel):
    query_id: str
    query_text: str
    retrieval_profile_version: str
    items: list[KnowledgeEvidenceItem]
    scope_applied: AppliedKnowledgeScope
    warnings: list[str] = Field(default_factory=list)
    dropped_foreign_tenant_count: int = 0
    created_at: datetime


class KnowledgeContextPack(BaseModel):
    query_text: str
    retrieval_profile_version: str
    query_id: str
    evidence: list[KnowledgeEvidenceItem]
    citations: list[str]
    scope: AppliedKnowledgeScope
    warnings: list[str]
    bounded_text: str
    truncated_item_count: int = 0
    truncated_character_count: int = 0
