from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import ConceptPrerequisite, CurriculumNode, CurriculumVersion
from app.models.enums import CurriculumNodeType
from app.prerequisite_intelligence.authority import (
    GraphAuthorityContext,
    build_graph_authority_context,
    load_revision_record,
    revision_is_authorized_for_scope,
)
from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    PrerequisiteGraphEdge,
    PrerequisiteGraphNode,
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import (
    EdgeProvenanceClass,
    GraphIssueCode,
    GraphLifecycleStatus,
)
from app.prerequisite_intelligence.stable_ids import stable_snapshot_id


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


def _classify_edge_provenance(
    session: Session,
    scope: PrerequisiteGraphScope,
    authority: GraphAuthorityContext,
    meta: dict[str, Any],
) -> tuple[EdgeProvenanceClass, str | None, str | None, list[GraphIssue]]:
    issues: list[GraphIssue] = []
    raw_claim = str(meta.get("provenance_class") or EdgeProvenanceClass.SYNTHETIC.value).lower()
    revision_id = meta.get("source_revision_id")
    locator = meta.get("source_locator")
    force_synthetic = bool(
        meta.get("synthetic")
        or meta.get("synthetic_fixture")
        or meta.get("fixture")
    )

    if force_synthetic:
        return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues

    if raw_claim not in {item.value for item in EdgeProvenanceClass}:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.MISSING_PROVENANCE,
                severity="warning",
                field_path="edges/metadata_json/provenance_class",
            )
        )
        return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues

    provenance = EdgeProvenanceClass(raw_claim)
    if provenance != EdgeProvenanceClass.OFFICIAL:
        return provenance, revision_id, locator, issues

    if not revision_id or not str(locator or "").strip():
        issues.append(
            GraphIssue(
                code=GraphIssueCode.MISSING_PROVENANCE,
                severity="error",
                field_path="edges/source_revision_id",
            )
        )
        return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues

    record = authority.revisions.get(str(revision_id))
    if record is None:
        record = load_revision_record(session, str(revision_id))
    if record is None:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                severity="error",
                field_path="edges/source_revision_id",
                detail={"source_revision_id": revision_id},
            )
        )
        return EdgeProvenanceClass.SYNTHETIC, str(revision_id), locator, issues

    if not revision_is_authorized_for_scope(record, scope, authority.curriculum_version_id):
        issues.append(
            GraphIssue(
                code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                severity="error",
                field_path="edges/source_revision_id",
                detail={"source_revision_id": revision_id},
            )
        )
        return EdgeProvenanceClass.SYNTHETIC, str(revision_id), locator, issues

    if str(revision_id) not in authority.authorized_revision_ids:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                severity="error",
                field_path="edges/source_revision_id",
                detail={"source_revision_id": revision_id},
            )
        )
        return EdgeProvenanceClass.SYNTHETIC, str(revision_id), locator, issues

    return EdgeProvenanceClass.OFFICIAL, str(revision_id), locator, issues


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

    authority = build_graph_authority_context(session, scope)

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

    if concept_ids:
        raw_edges = session.scalars(
            select(ConceptPrerequisite).where(
                ConceptPrerequisite.prerequisite_concept_id.in_(concept_ids),
                ConceptPrerequisite.target_concept_id.in_(concept_ids),
            )
        ).all()
    else:
        raw_edges = []

    edges: list[PrerequisiteGraphEdge] = []
    loader_issues: list[GraphIssue] = list(authority.issues)
    for edge in raw_edges:
        meta = dict(edge.metadata_json or {})
        provenance, source_revision_id, source_locator, edge_issues = _classify_edge_provenance(
            session, scope, authority, meta
        )
        loader_issues.extend(edge_issues)
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
                metadata_json=meta,
            )
        )
    edges.sort(key=lambda e: (e.prerequisite_concept_id, e.target_concept_id))

    checksum = PrerequisiteGraphSnapshot.compute_checksum(scope, nodes, edges, graph_version)
    snapshot_id = stable_snapshot_id(checksum, graph_version)
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
        metadata_json={
            "curriculum_version_code": version.version_code,
            "authorized_revision_ids": sorted(authority.authorized_revision_ids),
            "loader_issue_count": len(loader_issues),
        },
    )
