"""D16-04/D16-11 internal synthetic prerequisite graph — friction remediation fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from app.prerequisite_intelligence.contracts import (
    PrerequisiteGraphEdge,
    PrerequisiteGraphNode,
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphLifecycleStatus

_SYNTHETIC_GRAPH_VERSION = "d16-synth-physics-v1"


def build_friction_remediation_graph() -> PrerequisiteGraphSnapshot:
    """Original synthetic graph: friction (target) ← normal-force ← newton-laws."""
    scope = PrerequisiteGraphScope(
        curriculum_version_id="synthetic-d16-physics-v1",
        grade_year_code="grade-11",
        subject_code="physics",
    )
    nodes = [
        PrerequisiteGraphNode(
            concept_id="d16-c-newton-laws",
            concept_code="newton-laws",
            title="Newton's laws of motion",
            grade_year_code="grade-11",
            subject_code="physics",
        ),
        PrerequisiteGraphNode(
            concept_id="d16-c-normal-force",
            concept_code="normal-force",
            title="Normal force",
            grade_year_code="grade-11",
            subject_code="physics",
        ),
        PrerequisiteGraphNode(
            concept_id="d16-c-friction",
            concept_code="friction-applications",
            title="Friction in applications",
            grade_year_code="grade-11",
            subject_code="physics",
        ),
        PrerequisiteGraphNode(
            concept_id="d16-c-formula-selection",
            concept_code="friction-formula-selection",
            title="Selecting friction formulas",
            grade_year_code="grade-11",
            subject_code="physics",
        ),
    ]
    edges = [
        PrerequisiteGraphEdge(
            edge_id="d16-e1",
            prerequisite_concept_id="d16-c-newton-laws",
            target_concept_id="d16-c-normal-force",
            provenance_class=EdgeProvenanceClass.SYNTHETIC,
            weight=0.9,
        ),
        PrerequisiteGraphEdge(
            edge_id="d16-e2",
            prerequisite_concept_id="d16-c-normal-force",
            target_concept_id="d16-c-friction",
            provenance_class=EdgeProvenanceClass.SYNTHETIC,
            weight=0.85,
        ),
        PrerequisiteGraphEdge(
            edge_id="d16-e3",
            prerequisite_concept_id="d16-c-friction",
            target_concept_id="d16-c-formula-selection",
            provenance_class=EdgeProvenanceClass.SYNTHETIC,
            weight=0.8,
        ),
    ]
    checksum = PrerequisiteGraphSnapshot.compute_checksum(
        scope, nodes, edges, _SYNTHETIC_GRAPH_VERSION
    )
    return PrerequisiteGraphSnapshot(
        snapshot_id="d16-friction-snapshot",
        scope=scope,
        graph_version=_SYNTHETIC_GRAPH_VERSION,
        lifecycle_status=GraphLifecycleStatus.DRAFT,
        nodes=nodes,
        edges=edges,
        checksum=checksum,
        assembled_at=datetime.now(UTC).isoformat(),
        metadata_json={"fixture": "d16-friction-remediation", "actionable": False},
    )
