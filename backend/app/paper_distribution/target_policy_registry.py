from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.registry_versions import RegistryVersionNotFound
from app.models.education_intelligence import PolicyRegistryEntry
from app.paper_distribution.contracts import PaperDistributionRequest

PAPER_TARGET_POLICY_VERSION = "paper-distribution-targets@v1"
PAPER_TARGET_REGISTRY_KEY = "paper_distribution"

_DEFAULT_PAYLOAD: dict[str, Any] = {
    "allowed_cognitive_keys": [
        "remember",
        "understand",
        "apply",
        "analyze",
        "evaluate",
    ],
    "allowed_competency_keys": [
        "knowledge",
        "conceptual_understanding",
        "application",
        "analysis",
        "problem_solving",
        "hots",
    ],
}


def seed_paper_target_policy_registry(session: Session) -> dict[str, Any]:
    existing = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == PAPER_TARGET_REGISTRY_KEY,
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
            PolicyRegistryEntry.status == "active",
        )
    )
    if existing is None:
        session.add(
            PolicyRegistryEntry(
                registry_key=PAPER_TARGET_REGISTRY_KEY,
                version=PAPER_TARGET_POLICY_VERSION,
                status="active",
                payload_json=dict(_DEFAULT_PAYLOAD),
            )
        )
        session.flush()
        return dict(_DEFAULT_PAYLOAD)
    return dict(existing.payload_json or {})


def load_active_paper_target_policy(session: Session, version: str) -> dict[str, Any]:
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == PAPER_TARGET_REGISTRY_KEY,
            PolicyRegistryEntry.version == version,
            PolicyRegistryEntry.status == "active",
        )
    )
    if row is None:
        raise RegistryVersionNotFound("paper_distribution_policy", version)
    return dict(row.payload_json or {})


def paper_targets_authorized(
    session: Session,
    request: PaperDistributionRequest,
    *,
    version: str,
) -> tuple[bool, str | None]:
    if not request.cognitive_targets and not request.competency_targets:
        return True, None
    try:
        payload = load_active_paper_target_policy(session, version)
    except RegistryVersionNotFound:
        return False, "target_policy_version"
    allowed_cognitive = set(payload.get("allowed_cognitive_keys") or [])
    allowed_competency = set(payload.get("allowed_competency_keys") or [])
    for index, target in enumerate(request.cognitive_targets):
        if target.key not in allowed_cognitive:
            return False, f"cognitive_targets[{index}]/key"
    for index, target in enumerate(request.competency_targets):
        if target.key not in allowed_competency:
            return False, f"competency_targets[{index}]/key"
    return True, None
