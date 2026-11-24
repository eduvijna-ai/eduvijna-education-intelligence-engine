"""D16-11..D16-15 prerequisite remediation ordering (pure graph)."""

from __future__ import annotations

from collections import defaultdict, deque

from app.adaptive_remediation.contracts import RemediationTarget
from app.adaptive_remediation.enums import RemediationVerdict
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle
from app.adaptive_remediation.policy import map_strategy
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphSnapshot
from app.prerequisite_intelligence.enums import GraphAuditStatus


def graph_ready(
    snapshot: PrerequisiteGraphSnapshot,
) -> tuple[bool, RemediationVerdict, tuple[str, ...]]:
    report = build_graph_quality_report(snapshot)
    if report.status is GraphAuditStatus.FAIL:
        return False, RemediationVerdict.NOT_READY, tuple(i.code.value for i in report.issues[:5])
    if report.status is GraphAuditStatus.REVIEW_REQUIRED:
        return (
            False,
            RemediationVerdict.REVIEW_REQUIRED,
            tuple(i.code.value for i in report.issues[:5]),
        )
    return True, RemediationVerdict.DIAGNOSTIC_PLAN, ()


def foundation_first_order(
    snapshot: PrerequisiteGraphSnapshot,
    target_concept_id: str,
    *,
    budget: int,
) -> tuple[str, ...]:
    """Topological foundation-first sequence toward target, deduplicated, bounded."""
    by_id = {n.concept_id: n for n in snapshot.nodes}
    if target_concept_id not in by_id:
        return ()

    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in snapshot.edges:
        incoming[edge.target_concept_id].add(edge.prerequisite_concept_id)
        outgoing[edge.prerequisite_concept_id].add(edge.target_concept_id)

    ancestors: set[str] = set()
    queue: deque[str] = deque([target_concept_id])
    visited: set[str] = set()
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        ancestors.add(node)
        for pred in incoming.get(node, ()):
            queue.append(pred)

    indegree = {nid: len(incoming.get(nid, ())) for nid in ancestors}
    ready = sorted(nid for nid in ancestors if indegree[nid] == 0)
    order: list[str] = []
    while ready and len(order) < budget:
        nid = ready.pop(0)
        order.append(by_id[nid].concept_code)
        for child in sorted(outgoing.get(nid, ())):
            if child not in ancestors:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    return tuple(dict.fromkeys(order))


def build_prerequisite_targets(
    snapshot: PrerequisiteGraphSnapshot,
    bundle: NormalizedEvidenceBundle,
    target_concept_code: str,
    *,
    budget: int = 6,
) -> tuple[RemediationTarget, ...]:
    by_code = {n.concept_code: n for n in snapshot.nodes}
    target_node = by_code.get(target_concept_code)
    if target_node is None:
        return ()
    order = foundation_first_order(snapshot, target_node.concept_id, budget=budget)
    obs_by_concept = {o.concept_code: o for o in bundle.accepted}
    targets: list[RemediationTarget] = []
    for code in order:
        obs = obs_by_concept.get(code)
        if obs is None:
            continue
        targets.append(
            map_strategy(
                obs, prerequisite_of=target_concept_code if code != target_concept_code else None
            )
        )
    return tuple(targets)
