"""Day 16 adaptive remediation diagnostic service."""

from __future__ import annotations

import uuid
from datetime import date

from app.adaptive_remediation.adaptation import decide_adaptation, propose_spacing
from app.adaptive_remediation.containment import CONTAINMENT_NOTE, SYNTHETIC_DIAGNOSTIC_ONLY
from app.adaptive_remediation.contracts import (
    AdaptiveRemediationPlan,
    AdaptiveRemediationRequest,
    CurriculumScopeRef,
    EvidenceObservation,
    LearnerHistoryRef,
    ProductionRemediationGate,
    TeacherPolicyOverride,
)
from app.adaptive_remediation.enums import (
    AdaptationDecision,
    CorrectionPatternKind,
    EvidenceSupportLevel,
    RemediationVerdict,
)
from app.adaptive_remediation.evidence import (
    NormalizedEvidenceBundle,
    cold_start_required,
    normalize_observations,
)
from app.adaptive_remediation.fingerprint import plan_fingerprint
from app.adaptive_remediation.policy import (
    POLICY_VERSION,
    map_strategy,
    policy_verdict_for_cold_start,
    rank_concept_needs,
)
from app.adaptive_remediation.practice_plan import build_stage_blueprints, count_conservation_ok
from app.adaptive_remediation.prerequisite_plan import (
    build_prerequisite_targets,
    graph_ready,
)
from app.adaptive_remediation.production_gate import (
    production_remediation_gate,
    runtime_injection_blocked,
    trust_bypass_requested,
)
from app.adaptive_remediation.synthetic_catalogue import internal_synthetic_catalogue
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.adaptive_remediation.teacher_policy import apply_teacher_policy


class AdaptiveRemediationDiagnosticService:
    """Pure diagnostic planning — production remediation unconditionally NOT_READY."""

    def plan(
        self,
        request: AdaptiveRemediationRequest,
        *,
        teacher_override: TeacherPolicyOverride | None = None,
        **injected: object,
    ) -> AdaptiveRemediationPlan:
        safe, inj_issues = runtime_injection_blocked(**injected)
        bypass_ok, bypass_issues = trust_bypass_requested(**injected)
        gate = production_remediation_gate(
            reason=None if safe and bypass_ok else "CONTAINMENT_VIOLATION"
        )
        if not safe or not bypass_ok:
            gate = gate.model_copy(
                update={
                    "reason_codes": gate.reason_codes + inj_issues + bypass_issues,
                    "verdict": RemediationVerdict.BLOCKED,
                }
            )
            return _empty_plan(
                request,
                gate,
                explanation="Runtime injection or trust bypass blocked.",
                verdict=RemediationVerdict.BLOCKED,
            )

        bundle = normalize_observations(
            request.observations,
            curriculum_version_code=request.curriculum_scope.curriculum_version_code,
        )
        cold = cold_start_required(bundle, request.target_concept_code)
        verdict = policy_verdict_for_cold_start(cold)

        graph = build_friction_remediation_graph()
        g_ok, g_verdict, g_issues = graph_ready(graph)
        if not g_ok:
            verdict = g_verdict
            gate = production_remediation_gate(reason="GRAPH_NOT_READY")
            return _empty_plan(
                request,
                gate,
                explanation=f"Graph audit blocked: {', '.join(g_issues) or g_verdict.value}",
                verdict=verdict,
            )

        max_count = apply_teacher_policy(
            teacher_override,
            academic_max_count=min(
                request.requested_question_count, len(internal_synthetic_catalogue())
            ),
        )
        excluded = frozenset(request.history.excluded_question_ids if request.history else ())

        concept_order = tuple(
            n.concept_code
            for n in sorted(graph.nodes, key=lambda n: n.concept_code)
            if n.concept_code in {o.concept_code for o in bundle.accepted}
            or n.concept_code == request.target_concept_code
        )
        stages = build_stage_blueprints(
            max_count,
            concept_codes=concept_order or (request.target_concept_code,),
            excluded_question_ids=excluded,
        )
        if stages is None or not count_conservation_ok(stages, max_count):
            gate = production_remediation_gate(reason="ALLOCATION_INFEASIBLE")
            return _empty_plan(
                request,
                gate,
                explanation="Requested count cannot be allocated across synthetic stages.",
                verdict=RemediationVerdict.NOT_READY,
            )

        ranked = rank_concept_needs(bundle, target_concept_code=request.target_concept_code)
        targets = build_prerequisite_targets(graph, bundle, request.target_concept_code)
        if not targets and ranked:
            obs = bundle.accepted[0]
            targets = (map_strategy(obs),)

        adaptation, adapt_note = decide_adaptation(
            bundle,
            target_concept_code=request.target_concept_code,
            prior_cycle_count=0,
            practice_completed=False,
        )
        spacing = propose_spacing(request.as_of_date, 0)

        planned = sum(s.planned_count for s in stages)
        selected = sum(len(s.selected_synthetic_ids) for s in stages)
        fp = plan_fingerprint(request, policy_version=POLICY_VERSION)
        explanation = _build_explanation(
            request,
            bundle,
            cold,
            adaptation,
            adapt_note,
            spacing,
        )

        return AdaptiveRemediationPlan(
            plan_id=f"d16-plan-{uuid.uuid4().hex[:12]}",
            fingerprint=fp,
            verdict=verdict,
            policy_version=POLICY_VERSION,
            targets=targets,
            stages=stages,
            requested_count=request.requested_question_count,
            planned_count=planned,
            selected_count=selected,
            explanation=explanation,
            adaptation_decision=adaptation,
            production_gate=gate,
            metadata_json={
                "synthetic_diagnostic_only": SYNTHETIC_DIAGNOSTIC_ONLY,
                "containment_note": CONTAINMENT_NOTE,
                "graph_snapshot_id": graph.snapshot_id,
                "rejected_observations": bundle.rejected_ids,
                "cold_start": cold,
                "non_actionable": True,
            },
        )

    def build_authoritative_demo_request(self) -> AdaptiveRemediationRequest:
        """Internal friction fixture request — constructed inside diagnostic boundary."""
        return AdaptiveRemediationRequest(
            request_id="d16-internal-friction-demo",
            curriculum_scope=CurriculumScopeRef(
                curriculum_pack_code="d16-synth-physics",
                curriculum_version_code="d16-synth-physics-v1",
                subject_code="physics",
                grade_year_code="grade-11",
            ),
            target_concept_code="friction-formula-selection",
            observations=(
                EvidenceObservation(
                    observation_id="d16-obs-1",
                    concept_code="friction-formula-selection",
                    pattern_kind=CorrectionPatternKind.FORMULA,
                    support_level=EvidenceSupportLevel.RECURRENT,
                    curriculum_version_code="d16-synth-physics-v1",
                    uncertainty_note="Illustrative synthetic observation only.",
                ),
                EvidenceObservation(
                    observation_id="d16-obs-2",
                    concept_code="friction-applications",
                    pattern_kind=CorrectionPatternKind.APPLICATION,
                    support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
                    curriculum_version_code="d16-synth-physics-v1",
                ),
            ),
            history=LearnerHistoryRef(
                history_slot="synthetic-slot-a",
                excluded_question_ids=("d16-q-nl-01",),
            ),
            requested_question_count=10,
            as_of_date=date(2026, 11, 24),
        )

    def run_authoritative_synthetic_demo(self) -> AdaptiveRemediationPlan:
        """Internal friction fixture — caller cannot supply enabling proof."""
        return self.plan(self.build_authoritative_demo_request())


def _empty_plan(
    request: AdaptiveRemediationRequest,
    gate: ProductionRemediationGate,
    *,
    explanation: str,
    verdict: RemediationVerdict = RemediationVerdict.NOT_READY,
) -> AdaptiveRemediationPlan:
    fp = plan_fingerprint(request, policy_version=POLICY_VERSION)
    return AdaptiveRemediationPlan(
        plan_id=f"d16-plan-empty-{uuid.uuid4().hex[:8]}",
        fingerprint=fp,
        verdict=verdict,
        policy_version=POLICY_VERSION,
        targets=(),
        stages=(),
        requested_count=request.requested_question_count,
        planned_count=0,
        selected_count=0,
        explanation=explanation,
        adaptation_decision=decide_adaptation(
            normalize_observations(
                request.observations,
                curriculum_version_code=request.curriculum_scope.curriculum_version_code,
            ),
            target_concept_code=request.target_concept_code,
            prior_cycle_count=0,
            practice_completed=False,
        )[0],
        production_gate=gate,
        metadata_json={"non_actionable": True},
    )


def _build_explanation(
    request: AdaptiveRemediationRequest,
    bundle: NormalizedEvidenceBundle,
    cold: bool,
    adaptation: AdaptationDecision,
    adapt_note: str,
    spacing: date | None,
) -> str:
    parts = [
        "Synthetic diagnostic remediation plan (not actionable).",
        f"Target: {request.target_concept_code}.",
        f"Cold-start assessment need: {cold}.",
        f"Adaptation (illustrative): {adaptation.value} — {adapt_note}",
    ]
    if spacing:
        parts.append(f"Proposed spacing (not scheduled): {spacing.isoformat()}")
    if bundle.issue_codes:
        parts.append(f"Evidence normalization: {', '.join(bundle.issue_codes)}")
    return " ".join(parts)
