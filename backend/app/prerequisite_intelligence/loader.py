from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import ConceptPrerequisite, CurriculumNode, CurriculumVersion
from app.models.enums import CurriculumNodeType
from app.prerequisite_intelligence.contracts import (
    PrerequisiteGraphEdge,
    PrerequisiteGraphNode,
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphLifecycleStatus


def _node_scope_metadata(node: CurriculumNode) -> dict[str, Any]:
    meta = dict(node.metadata_json or {})
    parent = node.parent
    subject_code = None
    if parent is not None and parent.node_type == CurriculumNodeType.SUBJECT.value:
        subject_code = parent.code
    elif node.parent_id:
        subject_code = meta.get("subject_code")
    return {
        "grade_year_code": meta.get("grade_year_code"),
        "subject_code": subject_code or meta.get("subject_code"),
    }


def _edge_provenance(
    edge: ConceptPrerequisite,
) -> tuple[EdgeProvenanceClass, str | None, str | None]:
    meta = dict(edge.metadata_json or {})
    raw = str(meta.get("provenance_class") or "synthetic").lower()
    try:
        provenance = EdgeProvenanceClass(raw)
    except ValueError:
        provenance = EdgeProvenanceClass.SYNTHETIC
    return (
        provenance,
        meta.get("source_revision_id"),
        meta.get("source_locator"),
    )


def load_prerequisite_graph_snapshot(
    session: Session,
    scope: PrerequisiteGraphScope,
    *,
    graph_version: str = "prerequisite-graph@v1",
    lifecycle_status: GraphLifecycleStatus = GraphLifecycleStatus.ACTIVE,
    lineage_parent_snapshot_id: str | None = None,
) -> PrerequisiteGraphSnapshot:
    version = session.get(CurriculumVersion, scope.curriculum_version_id)
    if version is None:
        raise ValueError("curriculum_version_id not found")

    concept_nodes = session.scalars(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == scope.curriculum_version_id,
            CurriculumNode.node_type == CurriculumNodeType.CONCEPT.value,
        )
    ).all()

    filtered: list[CurriculumNode] = []
    for node in concept_nodes:
        node_meta = _node_scope_metadata(node)
        if scope.subject_code and node_meta.get("subject_code") != scope.subject_code:
            continue
        if scope.grade_year_code and node_meta.get("grade_year_code") != scope.grade_year_code:
            continue
        filtered.append(node)

    concept_ids = {node.id for node in filtered}
    nodes = [
        PrerequisiteGraphNode(
            concept_id=node.id,
            concept_code=node.code,
            title=node.title,
            grade_year_code=_node_scope_metadata(node).get("grade_year_code"),
            subject_code=_node_scope_metadata(node).get("subject_code"),
            active=True,
            metadata_json=dict(node.metadata_json or {}),
        )
        for node in sorted(filtered, key=lambda n: n.code)
    ]

    raw_edges = session.scalars(select(ConceptPrerequisite)).all()
    edges: list[PrerequisiteGraphEdge] = []
    for edge in raw_edges:
        if edge.prerequisite_concept_id not in concept_ids:
            continue
        if edge.target_concept_id not in concept_ids:
            continue
        provenance, source_revision_id, source_locator = _edge_provenance(edge)
        edges.append(
            PrerequisiteGraphEdge(
                edge_id=edge.id,
                prerequisite_concept_id=edge.prerequisite_concept_id,
                target_concept_id=edge.target_concept_id,
                relation_type=edge.relation_type,
                weight=edge.weight,
                provenance_class=provenance,
                source_revision_id=source_revision_id,
                source_locator=source_locator,
                metadata_json=dict(edge.metadata_json or {}),
            )
        )
    edges.sort(key=lambda e: (e.prerequisite_concept_id, e.target_concept_id))

    checksum = PrerequisiteGraphSnapshot.compute_checksum(scope, nodes, edges, graph_version)
    snapshot_id = str(uuid4())
    return PrerequisiteGraphSnapshot(
        snapshot_id=snapshot_id,
        scope=scope,
        graph_version=graph_version,
        lifecycle_status=lifecycle_status,
        nodes=nodes,
        edges=edges,
        checksum=checksum,
        lineage_parent_snapshot_id=lineage_parent_snapshot_id,
        assembled_at=datetime.now(UTC).isoformat(),
        metadata_json={"curriculum_version_code": version.version_code},
    )
