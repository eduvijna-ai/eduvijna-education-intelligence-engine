from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    PrerequisiteGraphEdge,
    PrerequisiteGraphNode,
    PrerequisiteGraphScope,
)
from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphIssueCode


def validate_edge_integrity(
    nodes: Iterable[PrerequisiteGraphNode],
    edges: Iterable[PrerequisiteGraphEdge],
    *,
    allowed_source_revision_ids: set[str] | None = None,
    require_official_authorization: bool = True,
) -> list[GraphIssue]:
    issues: list[GraphIssue] = []
    node_ids = {node.concept_id for node in nodes}
    node_by_id = {node.concept_id: node for node in nodes}
    seen: set[tuple[str, str]] = set()
    allowlist = set(allowed_source_revision_ids or [])

    for edge in edges:
        pair = (edge.prerequisite_concept_id, edge.target_concept_id)
        if edge.prerequisite_concept_id == edge.target_concept_id:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.SELF_EDGE,
                    severity="error",
                    field_path=f"edges/{edge.edge_id}",
                )
            )
        if pair in seen:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.DUPLICATE_EDGE,
                    severity="error",
                    field_path=f"edges/{edge.edge_id}",
                )
            )
        seen.add(pair)
        if edge.prerequisite_concept_id not in node_ids:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNKNOWN_NODE,
                    severity="error",
                    field_path=f"edges/{edge.edge_id}/prerequisite_concept_id",
                )
            )
        if edge.target_concept_id not in node_ids:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.UNKNOWN_NODE,
                    severity="error",
                    field_path=f"edges/{edge.edge_id}/target_concept_id",
                )
            )
        if edge.weight is not None and not (0.0 <= edge.weight <= 1.0):
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.INVALID_WEIGHT,
                    severity="error",
                    field_path=f"edges/{edge.edge_id}/weight",
                )
            )

        if edge.provenance_class == EdgeProvenanceClass.OFFICIAL:
            if not edge.source_revision_id or not str(edge.source_locator or "").strip():
                issues.append(
                    GraphIssue(
                        code=GraphIssueCode.MISSING_PROVENANCE,
                        severity="error",
                        field_path=f"edges/{edge.edge_id}/source_revision_id",
                    )
                )
            elif require_official_authorization:
                if not allowlist:
                    issues.append(
                        GraphIssue(
                            code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                            severity="error",
                            field_path=f"edges/{edge.edge_id}/source_revision_id",
                        )
                    )
                elif edge.source_revision_id not in allowlist:
                    issues.append(
                        GraphIssue(
                            code=GraphIssueCode.UNAUTHORIZED_PROVENANCE,
                            severity="error",
                            field_path=f"edges/{edge.edge_id}/source_revision_id",
                            detail={"source_revision_id": edge.source_revision_id},
                        )
                    )

        prereq = node_by_id.get(edge.prerequisite_concept_id)
        target = node_by_id.get(edge.target_concept_id)
        if prereq and target:
            if (
                prereq.subject_code
                and target.subject_code
                and prereq.subject_code != target.subject_code
            ):
                issues.append(
                    GraphIssue(
                        code=GraphIssueCode.CROSS_SUBJECT_EDGE,
                        severity="error",
                        field_path=f"edges/{edge.edge_id}",
                    )
                )

    return issues


def detect_cycles(
    nodes: Iterable[PrerequisiteGraphNode],
    edges: Iterable[PrerequisiteGraphEdge],
    *,
    max_depth: int = 256,
) -> tuple[list[GraphIssue], list[str]]:
    issues: list[GraphIssue] = []
    cycle_edge_ids: list[str] = []
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.prerequisite_concept_id].append((edge.target_concept_id, edge.edge_id))

    visiting: set[str] = set()
    visited: set[str] = set()
    stack_edges: list[str] = []

    def visit(node_id: str, depth: int) -> None:
        if depth > max_depth:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.DEPTH_LIMIT_EXCEEDED,
                    severity="error",
                    field_path=f"concepts/{node_id}",
                )
            )
            return
        if node_id in visiting:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.CYCLE_DETECTED,
                    severity="error",
                    field_path=f"concepts/{node_id}",
                )
            )
            if stack_edges:
                cycle_edge_ids.append(stack_edges[-1])
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for target_id, edge_id in adjacency.get(node_id, []):
            stack_edges.append(edge_id)
            visit(target_id, depth + 1)
            stack_edges.pop()
        visiting.remove(node_id)
        visited.add(node_id)

    for node in nodes:
        if node.concept_id not in visited:
            visit(node.concept_id, 0)

    return issues, list(dict.fromkeys(cycle_edge_ids))


def validate_scope_isolation(
    scope: PrerequisiteGraphScope,
    *,
    revision_organization_id: str | None = None,
    revision_institution_id: str | None = None,
) -> list[GraphIssue]:
    issues: list[GraphIssue] = []
    if scope.organization_id and revision_organization_id:
        if scope.organization_id != revision_organization_id:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.FOREIGN_TENANT,
                    severity="error",
                    field_path="scope/organization_id",
                )
            )
    if scope.institution_id and revision_institution_id:
        if scope.institution_id != revision_institution_id:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.FOREIGN_TENANT,
                    severity="error",
                    field_path="scope/institution_id",
                )
            )
    return issues
