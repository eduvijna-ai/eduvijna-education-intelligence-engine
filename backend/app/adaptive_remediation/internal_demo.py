"""Authoritative internal synthetic plan — no external caller input."""

from __future__ import annotations

from app.adaptive_remediation.adaptation import decide_adaptation, propose_spacing
from app.adaptive_remediation.containment import CONTAINMENT_NOTE, SYNTHETIC_DIAGNOSTIC_ONLY
from app.adaptive_remediation.contracts import AdaptiveRemediationPlan
from app.adaptive_remediation.enums import RemediationVerdict
from app.adaptive_remediation.evidence import (
    _support_rank,
    best_target_evidence,
    cold_start_required,
    normalize_observations,
)
from app.adaptive_remediation.fingerprint import internal_plan_fingerprint
from app.adaptive_remediation.policy import (
    POLICY_LIMITATIONS,
    POLICY_RATIONALE,
    POLICY_VERSION,
    policy_verdict_for_cold_start,
)
from app.adaptive_remediation.practice_plan import (
    build_stage_blueprints,
    count_conservation_ok,
)
from app.adaptive_remediation.prerequisite_plan import build_prerequisite_targets, graph_ready
from app.adaptive_remediation.production_gate import production_remediation_gate
from app.adaptive_remediation.synthetic_catalogue import retest_items_target_bound
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_CONCEPT_CODES,
    AUTHORITATIVE_AS_OF,
    AUTHORITATIVE_CURRICULUM,
    AUTHORITATIVE_EVIDENCE_POLICY,
    AUTHORITATIVE_PLAN_ID,
    AUTHORITATIVE_POLICY_VERSION,
    AUTHORITATIVE_REQUESTED_COUNT,
    AUTHORITATIVE_TARGET_CONCEPT,
    INTERNAL_HISTORY,
    INTERNAL_OBSERVATIONS,
    SYNTHETIC_CATALOGUE_VERSION,
)
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph


def build_authoritative_synthetic_plan() -> AdaptiveRemediationPlan:
    gate = production_remediation_gate()
    graph = build_friction_remediation_graph()
    g_ok, g_verdict, g_issues = graph_ready(graph)
    if not g_ok or not retest_items_target_bound(AUTHORITATIVE_TARGET_CONCEPT):
        return _not_ready_plan(
            reason="GRAPH_OR_RETEST_NOT_READY",
            issues=g_issues,
            verdict=g_verdict,
        )

    bundle = normalize_observations(
        INTERNAL_OBSERVATIONS,
        curriculum_version_code=AUTHORITATIVE_CURRICULUM.curriculum_version_code,
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=AUTHORITATIVE_AS_OF,
        evidence_policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
    )
    if bundle.issue_codes:
        return _not_ready_plan(
            reason="EVIDENCE_NORMALIZATION_FAILED",
            issues=bundle.issue_codes,
            verdict=RemediationVerdict.NOT_READY,
        )

    excluded = frozenset(INTERNAL_HISTORY.excluded_question_ids)
    stages = build_stage_blueprints(
        AUTHORITATIVE_REQUESTED_COUNT,
        excluded_question_ids=excluded,
    )
    if stages is None or not count_conservation_ok(stages, AUTHORITATIVE_REQUESTED_COUNT):
        return _not_ready_plan(
            reason="ALLOCATION_INFEASIBLE",
            issues=(),
            verdict=RemediationVerdict.NOT_READY,
        )

    targets = build_prerequisite_targets(
        graph,
        bundle,
        AUTHORITATIVE_TARGET_CONCEPT,
    )
    cold = cold_start_required(bundle, AUTHORITATIVE_TARGET_CONCEPT)
    verdict = policy_verdict_for_cold_start(cold)

    pre = best_target_evidence(bundle, AUTHORITATIVE_TARGET_CONCEPT)
    pre_rank = _support_rank(pre.support_level) if pre else None
    adaptation, adapt_note = decide_adaptation(
        bundle,
        target_concept_code=AUTHORITATIVE_TARGET_CONCEPT,
        prior_cycle_count=0,
        practice_completed=False,
        pre_practice_rank=pre_rank,
    )
    spacing = propose_spacing(AUTHORITATIVE_AS_OF, 0)

    fp = internal_plan_fingerprint(
        graph_checksum=graph.checksum,
        catalogue_version=SYNTHETIC_CATALOGUE_VERSION,
        policy_version=AUTHORITATIVE_POLICY_VERSION,
        observations=bundle.accepted,
        history=INTERNAL_HISTORY,
        requested_count=AUTHORITATIVE_REQUESTED_COUNT,
        as_of=AUTHORITATIVE_AS_OF.isoformat(),
        teacher_override=None,
        stages=stages,
        targets_codes=tuple(t.concept_code for t in targets),
    )

    foundation_concepts = tuple(
        c for c in (t.concept_code for t in targets) if c in ("newton-laws", "normal-force")
    )
    explanation = (
        "Synthetic diagnostic only. Internal friction fixture: "
        f"foundation concepts {foundation_concepts or ()}; "
        f"target {AUTHORITATIVE_TARGET_CONCEPT}; "
        f"cold_start={cold}; adaptation={adaptation.value} ({adapt_note}). "
        f"Policy: {POLICY_RATIONALE} Limits: {POLICY_LIMITATIONS}"
    )
    if spacing:
        explanation += f" Spacing illustration {spacing.isoformat()} (not scheduled)."

    planned = sum(s.planned_count for s in stages)
    selected = sum(len(s.selected_synthetic_ids) for s in stages)

    return AdaptiveRemediationPlan(
        plan_id=AUTHORITATIVE_PLAN_ID,
        fingerprint=fp,
        verdict=verdict,
        policy_version=POLICY_VERSION,
        targets=targets,
        stages=stages,
        requested_count=AUTHORITATIVE_REQUESTED_COUNT,
        planned_count=planned,
        selected_count=selected,
        explanation=explanation,
        adaptation_decision=adaptation,
        production_gate=gate,
        metadata_json={
            "synthetic_diagnostic_only": SYNTHETIC_DIAGNOSTIC_ONLY,
            "containment_note": CONTAINMENT_NOTE,
            "graph_checksum": graph.checksum,
            "catalogue_version": SYNTHETIC_CATALOGUE_VERSION,
            "non_actionable": True,
            "caller_data_processed": False,
        },
    )


def _not_ready_plan(
    *,
    reason: str,
    issues: tuple[str, ...],
    verdict: RemediationVerdict,
) -> AdaptiveRemediationPlan:
    from app.adaptive_remediation.enums import AdaptationDecision

    gate = production_remediation_gate(reason=reason)
    return AdaptiveRemediationPlan(
        plan_id="d16-plan-not-ready",
        fingerprint="d16-plan-not-ready",
        verdict=verdict,
        policy_version=POLICY_VERSION,
        targets=(),
        stages=(),
        requested_count=0,
        planned_count=0,
        selected_count=0,
        explanation=f"Synthetic diagnostic blocked: {reason} {' '.join(issues)}".strip(),
        adaptation_decision=AdaptationDecision.INSUFFICIENT_EVIDENCE,
        production_gate=gate,
        metadata_json={"non_actionable": True, "caller_data_processed": False},
    )
