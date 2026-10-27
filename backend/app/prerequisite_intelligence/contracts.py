from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.prerequisite_intelligence.enums import (
    EdgeProvenanceClass,
    GraphAuditStatus,
    GraphIssueCode,
    GraphLifecycleStatus,
)


class PrerequisiteGraphScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_version_id: str
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None


class PrerequisiteGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    concept_code: str
    title: str
    grade_year_code: str | None = None
    subject_code: str | None = None
    active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrerequisiteGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    prerequisite_concept_id: str
    target_concept_id: str
    relation_type: str = "prerequisite"
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance_class: EdgeProvenanceClass
    source_revision_id: str | None = None
    source_locator: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrerequisiteGraphPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str
    concept_ids: list[str]
    edge_ids: list[str]
    depth: int
    total_weight: float


class PrerequisiteGraphSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    scope: PrerequisiteGraphScope
    graph_version: str
    lifecycle_status: GraphLifecycleStatus
    nodes: list[PrerequisiteGraphNode]
    edges: list[PrerequisiteGraphEdge]
    checksum: str
    lineage_parent_snapshot_id: str | None = None
    assembled_at: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def compute_checksum(
        scope: PrerequisiteGraphScope,
        nodes: list[PrerequisiteGraphNode],
        edges: list[PrerequisiteGraphEdge],
        graph_version: str,
    ) -> str:
        payload = {
            "scope": scope.model_dump(mode="json"),
            "graph_version": graph_version,
            "nodes": sorted(
                [n.model_dump(mode="json") for n in nodes],
                key=lambda x: x["concept_id"],
            ),
            "edges": sorted(
                [e.model_dump(mode="json") for e in edges],
                key=lambda x: (x["prerequisite_concept_id"], x["target_concept_id"]),
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GraphTraversalLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_depth: int = Field(default=8, ge=1, le=32)
    max_nodes: int = Field(default=64, ge=1, le=512)
    max_paths: int = Field(default=16, ge=1, le=128)


class GraphIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: GraphIssueCode
    severity: str
    field_path: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class GraphQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    status: GraphAuditStatus
    issues: list[GraphIssue] = Field(default_factory=list)
    disconnected_concept_ids: list[str] = Field(default_factory=list)
    cycle_edge_ids: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
