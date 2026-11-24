"""D16-30 deterministic plan fingerprint over normalized inputs."""

from __future__ import annotations

import hashlib
import json

from app.adaptive_remediation.contracts import (
    AdaptiveRemediationPlan,
    EvidenceObservation,
    LearnerHistoryRef,
    PracticeStageBlueprint,
    TeacherPolicyOverride,
)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def internal_plan_fingerprint(
    *,
    graph_checksum: str,
    catalogue_version: str,
    policy_version: str,
    observations: tuple[EvidenceObservation, ...],
    history: LearnerHistoryRef | None,
    requested_count: int,
    as_of: str,
    teacher_override: TeacherPolicyOverride | None,
    stages: tuple[PracticeStageBlueprint, ...],
    targets_codes: tuple[str, ...],
) -> str:
    body = {
        "graph_checksum": graph_checksum,
        "catalogue_version": catalogue_version,
        "policy_version": policy_version,
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
        "stages": [
            {
                "stage": s.stage.value,
                "planned": s.planned_count,
                "ids": list(s.selected_synthetic_ids),
                "concepts": list(s.concept_codes),
            }
            for s in stages
        ],
        "target_codes": list(targets_codes),
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def fingerprint_from_plan(plan: AdaptiveRemediationPlan) -> str:
    return plan.fingerprint
