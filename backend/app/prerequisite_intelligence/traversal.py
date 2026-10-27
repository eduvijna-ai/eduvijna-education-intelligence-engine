from __future__ import annotations

from collections import deque

from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    GraphTraversalLimits,
    PrerequisiteGraphEdge,
    PrerequisiteGraphPath,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import GraphIssueCode
from app.prerequisite_intelligence.stable_ids import stable_path_id


def _adjacency(
    edges: list[PrerequisiteGraphEdge],
) -> tuple[dict[str, list[PrerequisiteGraphEdge]], dict[str, list[PrerequisiteGraphEdge]]]:
    forward: dict[str, list[PrerequisiteGraphEdge]] = {}
    backward: dict[str, list[PrerequisiteGraphEdge]] = {}
    for edge in edges:
        forward.setdefault(edge.prerequisite_concept_id, []).append(edge)
        backward.setdefault(edge.target_concept_id, []).append(edge)
    for mapping in (forward, backward):
        for key in mapping:
            mapping[key].sort(key=lambda e: (e.target_concept_id, e.edge_id))
    return forward, backward


def bounded_ancestor_paths(
    snapshot: PrerequisiteGraphSnapshot,
    target_concept_id: str,
    limits: GraphTraversalLimits | None = None,
) -> tuple[list[PrerequisiteGraphPath], list[GraphIssue]]:
    limits = limits or GraphTraversalLimits()
    issues: list[GraphIssue] = []
    _, backward = _adjacency(snapshot.edges)
    paths: list[PrerequisiteGraphPath] = []
    queue: deque[tuple[str, list[str], list[str], float]] = deque()
    queue.append((target_concept_id, [target_concept_id], [], 0.0))
    visited_nodes: set[str] = set()
    max_queue = limits.max_nodes * limits.max_paths * 4

    while queue and len(paths) < limits.max_paths:
        if len(queue) > max_queue:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.PATH_BUDGET_EXHAUSTED,
                    severity="warning",
                )
            )
            break
        concept_id, concept_chain, edge_chain, weight_sum = queue.popleft()
        if len(concept_chain) > limits.max_depth + 1:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.DEPTH_LIMIT_EXCEEDED,
                    severity="warning",
                    field_path=f"concepts/{concept_id}",
                )
            )
            continue
        if len(visited_nodes) >= limits.max_nodes and concept_id not in visited_nodes:
            issues.append(
                GraphIssue(
                    code=GraphIssueCode.PATH_BUDGET_EXHAUSTED,
                    severity="warning",
                )
            )
            break
        visited_nodes.add(concept_id)

        incoming = backward.get(concept_id, [])
        if not incoming:
            if len(concept_chain) > 1:
                concept_tuple = tuple(reversed(concept_chain))
                paths.append(
                    PrerequisiteGraphPath(
                        path_id=stable_path_id(snapshot.checksum, concept_tuple),
                        concept_ids=list(reversed(concept_chain)),
                        edge_ids=list(reversed(edge_chain)),
                        depth=len(concept_chain) - 1,
                        total_weight=weight_sum,
                    )
                )
            continue

        for edge in incoming:
            next_id = edge.prerequisite_concept_id
            if next_id in concept_chain:
                continue
            edge_weight = edge.weight if edge.weight is not None else 1.0
            queue.append(
                (
                    next_id,
                    concept_chain + [next_id],
                    edge_chain + [edge.edge_id],
                    weight_sum + edge_weight,
                )
            )

    paths.sort(key=lambda p: (p.depth, -p.total_weight, p.concept_ids[0]))
    return paths[: limits.max_paths], issues


def bounded_descendant_concepts(
    snapshot: PrerequisiteGraphSnapshot,
    source_concept_id: str,
    limits: GraphTraversalLimits | None = None,
) -> list[str]:
    limits = limits or GraphTraversalLimits()
    forward, _ = _adjacency(snapshot.edges)
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(source_concept_id, 0)])
    while queue and len(seen) < limits.max_nodes:
        concept_id, depth = queue.popleft()
        if concept_id in seen:
            continue
        seen.add(concept_id)
        if depth >= limits.max_depth:
            continue
        for edge in forward.get(concept_id, []):
            queue.append((edge.target_concept_id, depth + 1))
    return sorted(seen)
