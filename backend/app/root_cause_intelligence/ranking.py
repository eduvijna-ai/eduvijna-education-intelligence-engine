from __future__ import annotations

from app.prerequisite_intelligence.contracts import (
    GraphIssue,
    GraphTraversalLimits,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.stable_ids import stable_hypothesis_id
from app.prerequisite_intelligence.traversal import bounded_ancestor_paths
from app.root_cause_intelligence.contracts import RootCauseHypothesis
from app.root_cause_intelligence.mapping_registry import MisconceptionConceptMapping


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
        hypotheses.append(
            RootCauseHypothesis(
                hypothesis_id=stable_hypothesis_id(
                    snapshot.checksum, mapping.misconception_code, concept_code, rank
                ),
                rank=rank,
                concept_id=concept_id,
                concept_code=concept_code,
                support_score=round(support, 4),
                paths=matching_paths[: limits.max_paths],
                evidence_revision_ids=list(mapping.source_revision_ids),
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
