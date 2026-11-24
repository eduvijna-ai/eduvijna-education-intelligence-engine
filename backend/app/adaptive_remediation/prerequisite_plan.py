"""D16-11..D16-15 prerequisite remediation ordering (pure graph)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from app.adaptive_remediation.contracts import RemediationTarget
from app.adaptive_remediation.enums import (
    EvidenceSupportLevel,
    RemediationStrategyKind,
    RemediationVerdict,
)
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle
from app.adaptive_remediation.policy import map_strategy
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_GRAPH_SCOPE_VERSION,
    ALLOWED_GRAPH_SNAPSHOT_ID,
)
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphSnapshot
from app.prerequisite_intelligence.enums import GraphAuditStatus


@dataclass(frozen=True, slots=True)
class FoundationOrderResult:
    order: tuple[str, ...]
    complete: bool


def validate_fixture_graph_scope(
    snapshot: PrerequisiteGraphSnapshot,
) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    if snapshot.snapshot_id != ALLOWED_GRAPH_SNAPSHOT_ID:
        issues.append("SNAPSHOT_ID_MISMATCH")
    if snapshot.scope.curriculum_version_id != ALLOWED_GRAPH_SCOPE_VERSION:
        issues.append("SCOPE_VERSION_MISMATCH")
    return (len(issues) == 0, tuple(issues))


def graph_ready(
    snapshot: PrerequisiteGraphSnapshot,
) -> tuple[bool, RemediationVerdict, tuple[str, ...]]:
    scope_ok, scope_issues = validate_fixture_graph_scope(snapshot)
    if not scope_ok:
        return False, RemediationVerdict.NOT_READY, scope_issues
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
) -> FoundationOrderResult:
    by_id = {n.concept_id: n for n in snapshot.nodes}
    if target_concept_id not in by_id:
        return FoundationOrderResult(order=(), complete=False)

    for edge in snapshot.edges:
        if edge.prerequisite_concept_id not in by_id or edge.target_concept_id not in by_id:
            return FoundationOrderResult(order=(), complete=False)

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
    while ready:
        nid = ready.pop(0)
        order.append(by_id[nid].concept_code)
        for child in sorted(outgoing.get(nid, ())):
            if child not in ancestors:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    deduped = tuple(dict.fromkeys(order))
    if len(deduped) > budget:
        return FoundationOrderResult(order=(), complete=False)
    return FoundationOrderResult(order=deduped, complete=True)


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
    order_result = foundation_first_order(snapshot, target_node.concept_id, budget=budget)
    if not order_result.complete:
        return ()
    obs_by_concept = {o.concept_code: o for o in bundle.accepted}
    targets: list[RemediationTarget] = []
    for code in order_result.order:
        obs = obs_by_concept.get(code)
        if obs is not None:
            targets.append(
                map_strategy(
                    obs,
                    prerequisite_of=target_concept_code if code != target_concept_code else None,
                )
            )
            continue
        targets.append(
            RemediationTarget(
                concept_code=code,
                strategy=RemediationStrategyKind.ASSESSMENT_NEED,
                rationale="Prerequisite hypothesis from graph order; not verified weakness.",
                evidence_support=EvidenceSupportLevel.INSUFFICIENT,
                prerequisite_of=target_concept_code if code != target_concept_code else None,
            )
        )
    return tuple(targets)
