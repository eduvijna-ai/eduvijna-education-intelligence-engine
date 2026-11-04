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
    revision_permits_official_authority,
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


def _resolve_scope_from_ancestry(node: CurriculumNode) -> dict[str, Any]:
    grade_year_code: str | None = None
    medium_code: str | None = None
    subject_code: str | None = None
    current: CurriculumNode | None = node
    while current is not None:
        if current.node_type == CurriculumNodeType.GRADE_YEAR.value:
            grade_year_code = current.code
        elif current.node_type == CurriculumNodeType.MEDIUM.value:
            medium_code = current.code
        elif current.node_type == CurriculumNodeType.SUBJECT.value:
            subject_code = current.code
        current = current.parent

    meta = dict(node.metadata_json or {})
    conflicts: list[str] = []
    if meta.get("medium_code") and medium_code and meta.get("medium_code") != medium_code:
        conflicts.append("medium_code")
    meta_grade = meta.get("grade_year_code")
    if meta_grade and grade_year_code and meta_grade != grade_year_code:
        conflicts.append("grade_year_code")
    if meta.get("subject_code") and subject_code and meta.get("subject_code") != subject_code:
        conflicts.append("subject_code")

    is_fixture = False
    if node.curriculum_version is not None:
        is_fixture = bool((node.curriculum_version.metadata_json or {}).get("fixture"))
    metadata_only = bool(
        not is_fixture
        and (
            (not medium_code and meta.get("medium_code"))
            or (not grade_year_code and meta.get("grade_year_code"))
        )
    )
    return {
        "grade_year_code": grade_year_code or meta.get("grade_year_code"),
        "subject_code": subject_code or meta.get("subject_code"),
        "medium_code": medium_code if medium_code else meta.get("medium_code"),
        "scope_conflicts": conflicts,
        "scope_metadata_only": metadata_only,
    }


def _node_scope_metadata(node: CurriculumNode) -> dict[str, Any]:
    resolved = _resolve_scope_from_ancestry(node)
    if resolved.get("scope_conflicts") or resolved.get("scope_metadata_only"):
        return {**resolved, "excluded": True}
    return resolved


def _classify_edge_provenance(
    session: Session,
    scope: PrerequisiteGraphScope,
    authority: GraphAuthorityContext,
    meta: dict[str, Any],
    *,
    edge_id: str,
) -> tuple[EdgeProvenanceClass, str | None, str | None, list[GraphIssue], bool]:
    """Return provenance fields, issues, and whether the edge is trusted for traversal."""
    issues: list[GraphIssue] = []
    raw_claim = str(meta.get("provenance_class") or EdgeProvenanceClass.SYNTHETIC.value).lower()
    revision_id = meta.get("source_revision_id")
    locator = meta.get("source_locator")
    claimed_official = raw_claim == EdgeProvenanceClass.OFFICIAL.value

    if claimed_official:
        if not revision_id or not str(locator or "").strip():
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.MISSING_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "claimed": "official"},
                )
            )
            return EdgeProvenanceClass.OFFICIAL, revision_id, locator, issues, False

        record = authority.revisions.get(str(revision_id))
        if record is None:
            record = load_revision_record(session, str(revision_id))
        if record is None:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "source_revision_id": revision_id},
                )
            )
            return EdgeProvenanceClass.OFFICIAL, str(revision_id), locator, issues, False

        if not revision_is_authorized_for_scope(record, scope, authority.curriculum_version_id):
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "source_revision_id": revision_id},
                )
            )
            return EdgeProvenanceClass.OFFICIAL, str(revision_id), locator, issues, False

        if str(revision_id) not in authority.authorized_revision_ids:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "source_revision_id": revision_id},
                )
            )
            return EdgeProvenanceClass.OFFICIAL, str(revision_id), locator, issues, False

        if not revision_permits_official_authority(record):
            provenance = EdgeProvenanceClass.INFERRED
            if authority.production_graph:
                issues.append(
                    GraphIssue(
                        code=GraphIssueCode.MISSING_PROVENANCE,
                        severity="warning",
                        field_path=f"edges/{edge_id}/metadata_json/provenance_class",
                        detail={
                            "edge_id": edge_id,
                            "downgraded_from": EdgeProvenanceClass.OFFICIAL.value,
                            "source_type": record.source_type,
                        },
                    )
                )
            return provenance, str(revision_id), locator, issues, True

        return EdgeProvenanceClass.OFFICIAL, str(revision_id), locator, issues, True

    force_synthetic = bool(
        meta.get("synthetic") or meta.get("synthetic_fixture") or meta.get("fixture")
    )
    if force_synthetic:
        if authority.production_graph:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/metadata_json/synthetic",
                    detail={"edge_id": edge_id},
                )
            )
            return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues, False
        return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues, True

    if raw_claim not in {item.value for item in EdgeProvenanceClass}:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.MISSING_PROVENANCE,
                severity="warning",
                field_path=f"edges/{edge_id}/metadata_json/provenance_class",
                detail={"edge_id": edge_id},
            )
        )
        if authority.production_graph:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.MISSING_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/metadata_json/provenance_class",
                    detail={"edge_id": edge_id},
                )
            )
            return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues, False
        return EdgeProvenanceClass.SYNTHETIC, revision_id, locator, issues, True

    provenance = EdgeProvenanceClass(raw_claim)
    if provenance == EdgeProvenanceClass.SYNTHETIC and authority.production_graph:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                severity="error",
                field_path=f"edges/{edge_id}/metadata_json/provenance_class",
                detail={"edge_id": edge_id, "provenance": provenance.value},
            )
        )
        return provenance, revision_id, locator, issues, False
    non_official = {EdgeProvenanceClass.SYNTHETIC, EdgeProvenanceClass.INFERRED}
    if provenance in non_official and not revision_id:
        if authority.production_graph:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.MISSING_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "provenance": provenance.value},
                )
            )
            return provenance, revision_id, locator, issues, False
    if revision_id:
        record = authority.revisions.get(str(revision_id))
        if record is None:
            record = load_revision_record(session, str(revision_id))
        if record is None or not revision_is_authorized_for_scope(
            record, scope, authority.curriculum_version_id
        ):
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                    severity="error",
                    field_path=f"edges/{edge_id}/source_revision_id",
                    detail={"edge_id": edge_id, "source_revision_id": revision_id},
                )
            )
            return provenance, str(revision_id), locator, issues, False
    return provenance, revision_id, locator, issues, True


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

    subject_nodes: list[CurriculumNode] = []
    for node in concept_nodes:
        node_meta = _node_scope_metadata(node)
        if node_meta.get("excluded"):
            continue
        resolved_subject = node_meta.get("subject_code")
        if scope.subject_code and resolved_subject != scope.subject_code:
            continue
        if scope.medium_code and node_meta.get("medium_code") != scope.medium_code:
            continue
        subject_nodes.append(node)

    if scope.grade_year_code:
        seed_ids = {
            node.id
            for node in subject_nodes
            if _node_scope_metadata(node).get("grade_year_code") == scope.grade_year_code
        }
        subject_ids = {node.id for node in subject_nodes}
        if subject_ids:
            seed_edges = session.scalars(
                select(ConceptPrerequisite).where(
                    ConceptPrerequisite.prerequisite_concept_id.in_(subject_ids),
                    ConceptPrerequisite.target_concept_id.in_(subject_ids),
                )
            ).all()
            closure = set(seed_ids)
            changed = True
            while changed:
                changed = False
                for edge in seed_edges:
                    if edge.target_concept_id in closure:
                        if edge.prerequisite_concept_id not in closure:
                            closure.add(edge.prerequisite_concept_id)
                            changed = True
            filtered = [node for node in subject_nodes if node.id in closure]
        else:
            filtered = []
    else:
        filtered = subject_nodes

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
        provenance, source_revision_id, source_locator, edge_issues, include = (
            _classify_edge_provenance(session, scope, authority, meta, edge_id=edge.id)
        )
        loader_issues.extend(edge_issues)
        if not include:
            continue
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
            "loader_issues": [issue.model_dump(mode="json") for issue in loader_issues],
            "synthetic_fixture": bool((version.metadata_json or {}).get("fixture")),
            "fixture": bool((version.metadata_json or {}).get("fixture")),
            "loader_attested": True,
            "loader_scope": {
                "curriculum_version_id": scope.curriculum_version_id,
                "organization_id": scope.organization_id,
                "institution_id": scope.institution_id,
                "teacher_id": scope.teacher_id,
                "medium_code": scope.medium_code,
                "subject_code": scope.subject_code,
                "grade_year_code": scope.grade_year_code,
            },
        },
    )
