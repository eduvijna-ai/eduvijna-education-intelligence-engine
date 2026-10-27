from __future__ import annotations

from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    GraphQualityReport,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import GraphAuditStatus, GraphIssueCode
from app.prerequisite_intelligence.validators import (
    detect_cycles,
    validate_edge_integrity,
)


def build_graph_quality_report(
    snapshot: PrerequisiteGraphSnapshot,
    *,
    allowed_source_revision_ids: set[str] | None = None,
) -> GraphQualityReport:
    issues = validate_edge_integrity(
        snapshot.nodes,
        snapshot.edges,
        allowed_source_revision_ids=allowed_source_revision_ids,
    )
    cycle_issues, cycle_edge_ids = detect_cycles(snapshot.nodes, snapshot.edges)
    issues.extend(cycle_issues)

    connected: set[str] = set()
    for edge in snapshot.edges:
        connected.add(edge.prerequisite_concept_id)
        connected.add(edge.target_concept_id)
    disconnected = [
        node.concept_id for node in snapshot.nodes if node.concept_id not in connected
    ]
    for concept_id in disconnected:
        issues.append(
            GraphIssue(
                code=GraphIssueCode.DISCONNECTED_CONCEPT,
                severity="warning",
                field_path=f"concepts/{concept_id}",
            )
        )

    has_error = any(item.severity == "error" for item in issues)
    has_warning = any(item.severity == "warning" for item in issues)
    if has_error:
        status = GraphAuditStatus.FAIL
    elif has_warning or disconnected:
        status = GraphAuditStatus.REVIEW_REQUIRED
    else:
        status = GraphAuditStatus.PASS

    return GraphQualityReport(
        snapshot_id=snapshot.snapshot_id,
        status=status,
        issues=issues,
        disconnected_concept_ids=disconnected,
        cycle_edge_ids=cycle_edge_ids,
        metadata_json={"checksum": snapshot.checksum},
    )
