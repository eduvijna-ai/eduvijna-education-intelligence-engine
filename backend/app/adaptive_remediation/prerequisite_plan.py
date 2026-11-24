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
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle, map_strategy_observations
from app.adaptive_remediation.policy import map_strategy
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_GRAPH_SCOPE_VERSION,
    ALLOWED_GRAPH_SNAPSHOT_ID,
    ALLOWED_GRAPH_VERSION,
    AUTHORITATIVE_TARGET_CONCEPT,
)
from app.adaptive_remediation.synthetic_graph import authoritative_graph_checksum
from app.adaptive_remediation.validation import require_strict_positive_int
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
    if snapshot.graph_version != ALLOWED_GRAPH_VERSION:
        issues.append("GRAPH_VERSION_MISMATCH")
    if snapshot.scope.subject_code != "physics" or snapshot.scope.grade_year_code != "grade-11":
        issues.append("SCOPE_SUBJECT_GRADE_MISMATCH")
    if snapshot.checksum != authoritative_graph_checksum():
        issues.append("GRAPH_CHECKSUM_MISMATCH")
    codes = [n.concept_code for n in snapshot.nodes]
    if len(codes) != len(set(codes)):
        issues.append("DUPLICATE_CONCEPT_CODE")
    ids = [n.concept_id for n in snapshot.nodes]
    if len(ids) != len(set(ids)):
        issues.append("DUPLICATE_CONCEPT_ID")
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
    budget: object,
) -> FoundationOrderResult:
    budget_n = require_strict_positive_int(budget)
    if budget_n is None:
        return FoundationOrderResult(order=(), complete=False)

    ready, _, _ = graph_ready(snapshot)
    if not ready:
        return FoundationOrderResult(order=(), complete=False)

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
    ready_nodes = sorted(nid for nid in ancestors if indegree[nid] == 0)
    order: list[str] = []
    processed = 0
    while ready_nodes:
        nid = ready_nodes.pop(0)
        order.append(by_id[nid].concept_code)
        processed += 1
        for child in sorted(outgoing.get(nid, ())):
            if child not in ancestors:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                ready_nodes.append(child)
                ready_nodes.sort()

    if processed != len(ancestors):
        return FoundationOrderResult(order=(), complete=False)

    deduped = tuple(dict.fromkeys(order))
    if len(deduped) != len(ancestors) or len(deduped) > budget_n:
        return FoundationOrderResult(order=(), complete=False)
    return FoundationOrderResult(order=deduped, complete=True)


def build_prerequisite_targets(
    snapshot: PrerequisiteGraphSnapshot,
    bundle: NormalizedEvidenceBundle,
    target_concept_code: str,
    *,
    budget: int = 6,
) -> tuple[RemediationTarget, ...]:
    if target_concept_code != AUTHORITATIVE_TARGET_CONCEPT:
        return ()
    by_code = {n.concept_code: n for n in snapshot.nodes}
    target_node = by_code.get(target_concept_code)
    if target_node is None:
        return ()
    order_result = foundation_first_order(snapshot, target_node.concept_id, budget=budget)
    if not order_result.complete:
        return ()
    obs_by_concept = map_strategy_observations(bundle)
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