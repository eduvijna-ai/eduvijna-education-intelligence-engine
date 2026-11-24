"""D16-30 deterministic plan fingerprint over normalized inputs."""

from __future__ import annotations

import hashlib
import json

from app.adaptive_remediation.contracts import AdaptiveRemediationPlan, AdaptiveRemediationRequest


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def plan_fingerprint(request: AdaptiveRemediationRequest, *, policy_version: str) -> str:
    body = {
        "request_id": request.request_id,
        "curriculum": request.curriculum_scope.model_dump(mode="json"),
        "exam": request.exam_scope.model_dump(mode="json") if request.exam_scope else None,
        "target": request.target_concept_code,
        "observations": sorted(
            (o.model_dump(mode="json") for o in request.observations),
            key=lambda x: x["observation_id"],
        ),
        "requested_count": request.requested_question_count,
        "as_of": request.as_of_date.isoformat(),
        "policy_version": policy_version,
        "history_slot": request.history.history_slot if request.history else None,
        "preferences": request.preferences.model_dump(mode="json") if request.preferences else None,
    }
    digest = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return digest


def fingerprint_from_plan(plan: AdaptiveRemediationPlan) -> str:
    return plan.fingerprint
