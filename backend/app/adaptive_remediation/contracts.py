"""Day 16 immutable plain-data contracts — no ORM or session fields."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.adaptive_remediation.enums import (
    AdaptationDecision,
    CognitiveLevel,
    CorrectionPatternKind,
    EvidenceSupportLevel,
    PracticeStageKind,
    RemediationStrategyKind,
    RemediationVerdict,
)


class CurriculumScopeRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    curriculum_pack_code: str
    curriculum_version_code: str
    subject_code: str | None = None
    grade_year_code: str | None = None


class ExamScopeRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exam_pack_code: str
    exam_version_code: str | None = None
    official_replica_claim: bool = False


class EvidenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    concept_code: str
    pattern_kind: CorrectionPatternKind
    support_level: EvidenceSupportLevel
    source_revision_id: str | None = None
    source_locator: str | None = None
    observed_at: datetime | None = None
    policy_version: str = "d16-evidence-v1"
    uncertainty_note: str | None = None
    curriculum_version_code: str


class LearnerHistoryRef(BaseModel):
    """Non-identifying synthetic history slot — never real learner IDs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    history_slot: str
    recent_concept_codes: tuple[str, ...] = ()
    excluded_question_ids: tuple[str, ...] = ()


class PreferenceHints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preferred_difficulty: Literal["foundation", "balanced", "challenge"] | None = None
    max_daily_practice_minutes: int | None = Field(default=None, ge=1, le=240)


class AdaptiveRemediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    curriculum_scope: CurriculumScopeRef
    exam_scope: ExamScopeRef | None = None
    target_concept_code: str
    observations: tuple[EvidenceObservation, ...] = ()
    history: LearnerHistoryRef | None = None
    preferences: PreferenceHints | None = None
    requested_question_count: int = Field(ge=1, le=200)
    as_of_date: date
    policy_version: str = "d16-adaptive-policy-v1"

    @field_validator("exam_scope")
    @classmethod
    def block_official_claim_without_scope(cls, v: ExamScopeRef | None) -> ExamScopeRef | None:
        if v is not None and v.official_replica_claim:
            raise ValueError("official_replica_claim_not_permitted_in_d16")
        return v


class ProductionRemediationGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    production_ready: bool = False
    actionable: bool = False
    delivered_question_count: int = 0
    validated_question_count: int = 0
    scheduled_event_count: int = 0
    persisted_plan_id: str | None = None
    learner_record_touched: bool = False
    verdict: RemediationVerdict = RemediationVerdict.NOT_READY
    reason_codes: tuple[str, ...] = ("D16_PRODUCTION_DISABLED",)

    @model_validator(mode="after")
    def enforce_output_only_containment(self) -> ProductionRemediationGate:
        if self.production_ready or self.actionable or self.learner_record_touched:
            raise ValueError("production_gate_elevation_forbidden")
        if self.persisted_plan_id is not None:
            raise ValueError("production_gate_persistence_forbidden")
        if any(
            c > 0
            for c in (
                self.delivered_question_count,
                self.validated_question_count,
                self.scheduled_event_count,
            )
        ):
            raise ValueError("production_gate_nonzero_delivery_forbidden")
        return self


class PracticeStageBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: PracticeStageKind
    concept_codes: tuple[str, ...]
    cognitive_level: CognitiveLevel
    difficulty_band: Literal["foundation", "standard", "application"]
    question_type: str
    marks_per_item: int = Field(ge=1, le=10)
    planned_count: int = Field(ge=0)
    selected_synthetic_ids: tuple[str, ...] = ()


class RemediationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    concept_code: str
    strategy: RemediationStrategyKind
    rationale: str
    evidence_support: EvidenceSupportLevel
    prerequisite_of: str | None = None


class AdaptiveRemediationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    fingerprint: str
    verdict: RemediationVerdict
    policy_version: str
    targets: tuple[RemediationTarget, ...]
    stages: tuple[PracticeStageBlueprint, ...]
    requested_count: int
    planned_count: int
    selected_count: int
    explanation: str
    adaptation_decision: AdaptationDecision
    production_gate: ProductionRemediationGate
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TeacherPolicyOverride(BaseModel):
    """Typed future override boundary — cannot weaken containment gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    override_id: str
    institution_scope: str | None = None
    allowed_max_count: int | None = Field(default=None, ge=1, le=200)
    allowed_difficulty_ceiling: str | None = None
    provenance: str
    precedence_rank: int = Field(ge=0, le=100)

    def effective_max_count(self, academic_max: int) -> int:
        if self.allowed_max_count is None:
            return academic_max
        return min(self.allowed_max_count, academic_max)
