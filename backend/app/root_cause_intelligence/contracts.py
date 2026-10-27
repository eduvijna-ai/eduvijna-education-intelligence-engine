from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.prerequisite_intelligence.contracts import PrerequisiteGraphPath, PrerequisiteGraphSnapshot
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus


class RootCauseDiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_key: str
    misconception_code: str
    taxonomy_version: str
    tag: OptionDiagnosticTag
    curriculum_version_id: str
    graph_snapshot: PrerequisiteGraphSnapshot
    target_concept_code: str
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None
    allowed_source_revision_ids: list[str] = Field(default_factory=list)
    day6_blocking: bool = False
    orchestration_run_id: str | None = None
    orchestration_request_hash: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RootCauseHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    rank: int
    concept_id: str
    concept_code: str
    support_score: float
    paths: list[PrerequisiteGraphPath]
    evidence_revision_ids: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    uncertainty_notes: str | None = None


class RootCauseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_key: str
    misconception_code: str
    verdict_status: RootCauseVerdictStatus
    issue_codes: list[RootCauseIssueCode] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)
    hypotheses: list[RootCauseHypothesis] = Field(default_factory=list)
    mapping_version: str
    graph_snapshot_id: str
    graph_checksum: str
    audit_ref: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
