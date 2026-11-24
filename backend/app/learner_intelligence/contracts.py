from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.learner_intelligence.enums import (
    AttemptState,
    EligibilityTrustMode,
    EligibilityVerdict,
    IssueCode,
    MasteryConfidence,
    MasteryLevel,
    PerformanceMode,
    ResponseKind,
    ScoringVerdict,
)


class TrustedActorContext(BaseModel):
    """Server-resolved tenant context; never authoritative from caller metadata alone."""

    model_config = ConfigDict(extra="forbid")

    organization_id: str
    institution_id: str
    learner_id: str
    resolved_by: str = "server_session"


class SnapshotOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    display_text: str
    is_correct: bool = False


class SnapshotItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_sequence: int
    question_id: str
    stem_text: str
    question_type: str
    options: list[SnapshotOption] = Field(default_factory=list)
    marks_if_correct: Decimal
    marks_if_incorrect: Decimal
    marks_if_blank: Decimal = Field(default=Decimal("0"))
    numeric_answer: str | None = None
    numeric_tolerance: Decimal | None = None
    concept_codes: list[str] = Field(default_factory=list)
    learning_outcome_ids: list[str] = Field(default_factory=list)
    competency_codes: list[str] = Field(default_factory=list)
    difficulty_band: str | None = None
    cognitive_level: str | None = None
    scoring_policy_version: str = "scoring@v1"
    source_version: str
    content_fingerprint: str
    diagnostic_tags_json: list[dict[str, Any]] = Field(default_factory=list)


class CreateAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: TrustedActorContext
    trust_mode: EligibilityTrustMode
    assessment_key: str
    exam_pack_code: str | None = None
    exam_version_id: str | None = None
    performance_mode: PerformanceMode = PerformanceMode.PRACTICE
    idempotency_key: str
    items: list[SnapshotItem]
    catalog_key: str | None = None
    harness_attestation: str | None = None


class RecordResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: TrustedActorContext
    attempt_id: str
    item_sequence: int
    response_kind: ResponseKind
    selected_option_keys: list[str] = Field(default_factory=list)
    numeric_value: str | None = None
    descriptive_text: str | None = None


class FinalizeAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: TrustedActorContext
    attempt_id: str
    idempotency_key: str
    content_binding_fingerprint: str


class AttemptOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    state: AttemptState
    eligibility_verdict: EligibilityVerdict
    issue_codes: list[IssueCode] = Field(default_factory=list)
    committed: bool = False
    total_marks: Decimal | None = None
    max_marks: Decimal | None = None
    item_outcomes: list[dict[str, Any]] = Field(default_factory=list)


class MasterySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_code: str
    level: MasteryLevel
    confidence: MasteryConfidence
    support_correct: int
    support_incorrect: int
    policy_version: str


class RemediationHandoff(BaseModel):
    """D15-31: evidence-backed gaps for Day 16; no scheduling."""

    model_config = ConfigDict(extra="forbid")

    readiness: str = "NOT_READY"
    learner_id: str
    organization_id: str
    institution_id: str
    concept_gaps: list[str] = Field(default_factory=list)
    misconception_codes: list[str] = Field(default_factory=list)
    prerequisite_hypothesis_ids: list[str] = Field(default_factory=list)
    source_attempt_ids: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    policy_version: str = "handoff@v1"
    actionable: bool = False
    synthetic_diagnostic_only: bool = False


class ItemScoreOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_sequence: int
    verdict: ScoringVerdict
    marks_awarded: Decimal
    max_marks: Decimal