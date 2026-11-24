"""D16-30 deterministic plan fingerprint over normalized inputs."""

from __future__ import annotations

import hashlib
import json

from app.adaptive_remediation.contracts import (
    AdaptiveRemediationPlan,
    EvidenceObservation,
    LearnerHistoryRef,
    PracticeStageBlueprint,
    RemediationTarget,
    TeacherPolicyOverride,
)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _stage_payload(stages: tuple[PracticeStageBlueprint, ...]) -> list[dict[str, object]]:
    return [
        {
            "stage": s.stage.value,
            "planned": s.planned_count,
            "ids": list(s.selected_synthetic_ids),
            "concepts": list(s.concept_codes),
            "cognitive_level": s.cognitive_level.value,
            "difficulty_band": s.difficulty_band,
            "question_type": s.question_type,
            "marks_per_item": s.marks_per_item,
            "metadata": s.metadata_json,
        }
        for s in stages
    ]


def _target_payload(targets: tuple[RemediationTarget, ...]) -> list[dict[str, object]]:
    return [
        {
            "concept_code": t.concept_code,
            "strategy": t.strategy.value,
            "support": t.evidence_support.value,
            "prerequisite_of": t.prerequisite_of,
            "rationale": t.rationale,
        }
        for t in targets
    ]


def internal_plan_fingerprint(
    *,
    graph_checksum: str,
    catalogue_version: str,
    policy_version: str,
    curriculum_version_code: str,
    target_concept_code: str,
    observations: tuple[EvidenceObservation, ...],
    history: LearnerHistoryRef | None,
    requested_count: int,
    as_of: str,
    teacher_override: TeacherPolicyOverride | None,
    stages: tuple[PracticeStageBlueprint, ...],
    targets: tuple[RemediationTarget, ...],
    adaptation_decision: str,
) -> str:
    body = {
        "graph_checksum": graph_checksum,
        "catalogue_version": catalogue_version,
        "policy_version": policy_version,
        "curriculum_version_code": curriculum_version_code,
        "target_concept_code": target_concept_code,
        "as_of": as_of,
        "requested_count": requested_count,
        "observations": sorted(
            (o.model_dump(mode="json") for o in observations),
            key=lambda x: x["observation_id"],
        ),
        "history_slot": history.history_slot if history else None,
        "excluded_question_ids": sorted(history.excluded_question_ids if history else ()),
        "recent_concept_codes": sorted(history.recent_concept_codes if history else ()),
        "teacher_override": teacher_override.model_dump(mode="json") if teacher_override else None,
        "stages": _stage_payload(stages),
        "targets": _target_payload(targets),
        "adaptation_decision": adaptation_decision,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def fingerprint_from_plan(plan: AdaptiveRemediationPlan) -> str:
    return plan.fingerprint


def plans_deterministically_equal(a: AdaptiveRemediationPlan, b: AdaptiveRemediationPlan) -> bool:
    return (
        a.fingerprint == b.fingerprint
        and a.model_dump(mode="json") == b.model_dump(mode="json")
    )