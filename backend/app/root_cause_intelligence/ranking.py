from __future__ import annotations

from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    GraphTraversalLimits,
    PrerequisiteGraphEdge,
    PrerequisiteGraphPath,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.stable_ids import stable_hypothesis_id
from app.prerequisite_intelligence.traversal import bounded_ancestor_paths
from app.root_cause_intelligence.contracts import RootCauseHypothesis
from app.root_cause_intelligence.mapping_registry import MisconceptionConceptMapping


def _path_authorized_for_option(
    snapshot_edges: list[PrerequisiteGraphEdge],
    path: PrerequisiteGraphPath,
    allowed: set[str],
) -> bool:
    edge_by_id = {edge.edge_id: edge for edge in snapshot_edges}
    sourced_revision_ids: list[str] = []
    for edge_id in path.edge_ids:
        edge = edge_by_id.get(edge_id)
        if edge is None or not edge.source_revision_id:
            continue
        sourced_revision_ids.append(str(edge.source_revision_id))
    if not sourced_revision_ids:
        return True
    if not allowed:
        return False
    return all(revision_id in allowed for revision_id in sourced_revision_ids)


def project_hypothesis_authorized_paths(
    snapshot: PrerequisiteGraphSnapshot,
    hypothesis: RootCauseHypothesis,
    allowed: set[str],
    mapping_source_revision_ids: list[str],
) -> RootCauseHypothesis | None:
    authorized_paths = [
        path
        for path in hypothesis.paths
        if _path_authorized_for_option(snapshot.edges, path, allowed)
    ]
    if not authorized_paths:
        return None
    path_evidence = _evidence_revision_ids_from_paths(snapshot, authorized_paths)
    mapping_evidence = [str(rev) for rev in mapping_source_revision_ids if rev]
    evidence_ids = sorted(set(path_evidence + mapping_evidence))
    support = hypothesis.support_score
    if len(authorized_paths) < len(hypothesis.paths):
        support = round(max(0.1, support * len(authorized_paths) / len(hypothesis.paths)), 4)
    return hypothesis.model_copy(
        update={
            "paths": authorized_paths,
            "evidence_revision_ids": evidence_ids,
            "support_score": support,
        }
    )


def _evidence_revision_ids_from_paths(
    snapshot: PrerequisiteGraphSnapshot,
    paths: list[PrerequisiteGraphPath],
) -> list[str]:
    edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
    revision_ids: list[str] = []
    for path in paths:
        for edge_id in path.edge_ids:
            edge = edge_by_id.get(edge_id)
            if edge is not None and edge.source_revision_id:
                revision_ids.append(str(edge.source_revision_id))
    return sorted(set(revision_ids))


def rank_root_cause_hypotheses(
    snapshot: PrerequisiteGraphSnapshot,
    mapping: MisconceptionConceptMapping,
    *,
    target_concept_code: str,
    limits: GraphTraversalLimits | None = None,
) -> tuple[list[RootCauseHypothesis], list[GraphIssue]]:
    limits = limits or GraphTraversalLimits(max_depth=6, max_paths=8, max_nodes=32)
    code_to_id = {node.concept_code: node.concept_id for node in snapshot.nodes}
    target_id = code_to_id.get(target_concept_code)
    if target_id is None:
        return [], []

    all_paths, traversal_issues = bounded_ancestor_paths(snapshot, target_id, limits)
    hypotheses: list[RootCauseHypothesis] = []
    for rank, concept_code in enumerate(mapping.candidate_concept_codes, start=1):
        concept_id = code_to_id.get(concept_code)
        if concept_id is None:
            continue
        matching_paths = [
            path
            for path in all_paths
            if concept_id in path.concept_ids and len(path.edge_ids) > 0
        ]
        if not matching_paths:
            continue
        support = 1.0 / rank
        support += min(0.5, 0.1 * len(matching_paths))
        support += max(0.0, 0.05 * (1.0 / matching_paths[0].depth))
        alternatives = [
            code for code in mapping.candidate_concept_codes if code != concept_code
        ]
        path_slice = matching_paths[: limits.max_paths]
        path_evidence = _evidence_revision_ids_from_paths(snapshot, path_slice)
        mapping_evidence = [str(rev) for rev in mapping.source_revision_ids if rev]
        evidence_ids = sorted(set(path_evidence + mapping_evidence))
        hypotheses.append(
            RootCauseHypothesis(
                hypothesis_id=stable_hypothesis_id(
                    snapshot.checksum, mapping.misconception_code, concept_code, rank
                ),
                rank=rank,
                concept_id=concept_id,
                concept_code=concept_code,
                support_score=round(support, 4),
                paths=path_slice,
                evidence_revision_ids=evidence_ids,
                alternatives=alternatives,
                uncertainty_notes=(
                    "Possible prerequisite mechanism; not demonstrated learner mastery."
                ),
            )
        )

    hypotheses.sort(key=lambda h: (-h.support_score, h.rank, h.concept_code))
    reranked: list[RootCauseHypothesis] = []
    for index, hypothesis in enumerate(hypotheses, start=1):
        reranked.append(
            hypothesis.model_copy(
                update={
                    "rank": index,
                    "hypothesis_id": stable_hypothesis_id(
                        snapshot.checksum,
                        mapping.misconception_code,
                        hypothesis.concept_code,
                        index,
                    ),
                }
            )
        )
    return reranked, traversal_issues
