from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.registry_versions import RegistryVersionNotFound
from app.models.education_intelligence import PolicyRegistryEntry
from app.paper_distribution.contracts import DistributionTarget, PaperDistributionRequest

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


def ensure_paper_target_policy_configured(session: Session) -> None:
    """Insert default policy only when no row has ever been stored for this version."""
    existing = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == PAPER_TARGET_REGISTRY_KEY,
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    if existing is not None:
        return
    session.add(
        PolicyRegistryEntry(
            registry_key=PAPER_TARGET_REGISTRY_KEY,
            version=PAPER_TARGET_POLICY_VERSION,
            status="active",
            payload_json=dict(_DEFAULT_PAYLOAD),
        )
    )
    session.flush()


def seed_paper_target_policy_registry(session: Session) -> dict[str, Any]:
    ensure_paper_target_policy_configured(session)
    return load_active_paper_target_policy(session, PAPER_TARGET_POLICY_VERSION)


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


def _overlay_mandatory_range(
    targets: list[DistributionTarget],
    *,
    dimension: str,
    key: str,
    entry: dict[str, Any],
) -> None:
    existing = next((target for target in targets if target.key == key), None)
    mandatory_min = entry.get("min_percent")
    mandatory_max = entry.get("max_percent")
    mandatory_count = entry.get("exact_count")
    if existing is None:
        targets.append(
            DistributionTarget(
                dimension=dimension,
                key=key,
                min_percent=mandatory_min,
                max_percent=mandatory_max,
                exact_count=mandatory_count,
            )
        )
        return
    new_min = existing.min_percent
    new_max = existing.max_percent
    if mandatory_min is not None:
        baseline_min = new_min if new_min is not None else mandatory_min
        new_min = max(float(mandatory_min), float(baseline_min))
    if mandatory_max is not None:
        baseline_max = new_max if new_max is not None else mandatory_max
        new_max = min(float(mandatory_max), float(baseline_max))
    update_fields: dict[str, Any] = {
        "min_percent": new_min,
        "max_percent": new_max,
    }
    if mandatory_count is not None:
        update_fields["exact_count"] = int(mandatory_count)
    updated = existing.model_copy(update=update_fields)
    index = targets.index(existing)
    targets[index] = updated


def mandatory_target_conflicts(
    request: PaperDistributionRequest,
    policy_payload: dict[str, Any],
) -> list[str]:
    item_count = len(request.items) if request.items else (request.requested_count or 0)
    conflicts: list[str] = []

    def _exact_percent_conflicts(
        targets: list[DistributionTarget],
        mandatory_map: dict[Any, Any],
        prefix: str,
    ) -> None:
        for key, mandatory_value in mandatory_map.items():
            key_str = str(key)
            mandatory = float(mandatory_value)
            for index, target in enumerate(targets):
                if target.key != key_str:
                    continue
                if target.exact_percent is not None:
                    delta = abs(target.exact_percent - mandatory)
                    if delta > 0.01:
                        conflicts.append(f"{prefix}[{index}]/exact_percent")

    def _range_conflicts(
        targets: list[DistributionTarget],
        mandatory_ranges: list[Any],
        prefix: str,
    ) -> None:
        for entry in mandatory_ranges:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "")
            if not key:
                continue
            mandatory_min = entry.get("min_percent")
            mandatory_max = entry.get("max_percent")
            mandatory_count = entry.get("exact_count")
            for index, target in enumerate(targets):
                if target.key != key:
                    continue
                if target.exact_percent is not None:
                    pct = target.exact_percent
                    if mandatory_min is not None and pct < float(mandatory_min) - 0.01:
                        conflicts.append(f"{prefix}[{index}]/exact_percent")
                    if mandatory_max is not None and pct > float(mandatory_max) + 0.01:
                        conflicts.append(f"{prefix}[{index}]/exact_percent")
                if mandatory_count is not None:
                    mandatory_int = int(mandatory_count)
                    if target.exact_count is not None and int(target.exact_count) != mandatory_int:
                        conflicts.append(f"{prefix}[{index}]/exact_count")
                    if (
                        item_count > 0
                        and target.exact_percent is not None
                        and abs(target.exact_percent - 100.0) < 0.01
                        and mandatory_int != item_count
                    ):
                        conflicts.append(f"{prefix}[{index}]/exact_count")
                    elif item_count > 0 and target.exact_percent is not None:
                        implied = int(
                            round(item_count * float(target.exact_percent) / 100.0)
                        )
                        if implied != mandatory_int:
                            conflicts.append(f"{prefix}[{index}]/exact_count")
                if (
                    target.min_percent is not None
                    and target.max_percent is not None
                    and mandatory_min is not None
                    and mandatory_max is not None
                ):
                    tightened_min = max(float(target.min_percent), float(mandatory_min))
                    tightened_max = min(float(target.max_percent), float(mandatory_max))
                    if tightened_min > tightened_max + 0.01:
                        conflicts.append(f"{prefix}[{index}]/range")

    _exact_percent_conflicts(
        list(request.cognitive_targets),
        policy_payload.get("mandatory_cognitive_exact_percent") or {},
        "cognitive_targets",
    )
    _exact_percent_conflicts(
        list(request.competency_targets),
        policy_payload.get("mandatory_competency_exact_percent") or {},
        "competency_targets",
    )
    _range_conflicts(
        list(request.cognitive_targets),
        policy_payload.get("mandatory_cognitive_ranges") or [],
        "cognitive_targets",
    )
    _range_conflicts(
        list(request.competency_targets),
        policy_payload.get("mandatory_competency_ranges") or [],
        "competency_targets",
    )
    return conflicts


def merge_mandatory_distribution_targets(
    request: PaperDistributionRequest,
    policy_payload: dict[str, Any],
) -> tuple[list[DistributionTarget], list[DistributionTarget]]:
    cognitive = list(request.cognitive_targets)
    competency = list(request.competency_targets)
    cognitive_keys = {target.key for target in cognitive}
    competency_keys = {target.key for target in competency}

    for key, approved in (policy_payload.get("mandatory_cognitive_exact_percent") or {}).items():
        key_str = str(key)
        if key_str in cognitive_keys:
            continue
        cognitive.append(
            DistributionTarget(
                dimension="cognitive",
                key=key_str,
                exact_percent=float(approved),
            )
        )
        cognitive_keys.add(key_str)

    for key, approved in (policy_payload.get("mandatory_competency_exact_percent") or {}).items():
        key_str = str(key)
        if key_str in competency_keys:
            continue
        competency.append(
            DistributionTarget(
                dimension="competency",
                key=key_str,
                exact_percent=float(approved),
            )
        )
        competency_keys.add(key_str)

    for entry in policy_payload.get("mandatory_cognitive_ranges") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if not key:
            continue
        _overlay_mandatory_range(cognitive, dimension="cognitive", key=key, entry=entry)
        cognitive_keys.add(key)

    for entry in policy_payload.get("mandatory_competency_ranges") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if not key:
            continue
        _overlay_mandatory_range(competency, dimension="competency", key=key, entry=entry)
        competency_keys.add(key)

    return cognitive, competency


def paper_targets_authorized(
    session: Session,
    request: PaperDistributionRequest,
    *,
    version: str,
) -> tuple[bool, str | None]:
    try:
        payload = load_active_paper_target_policy(session, version)
    except RegistryVersionNotFound:
        return False, "target_policy_version"

    conflict_paths = mandatory_target_conflicts(request, payload)
    if conflict_paths:
        return False, conflict_paths[0]

    cognitive, competency = merge_mandatory_distribution_targets(request, payload)
    if not cognitive and not competency:
        return True, None

    allowed_cognitive = set(payload.get("allowed_cognitive_keys") or [])
    allowed_competency = set(payload.get("allowed_competency_keys") or [])
    cognitive_quotas = payload.get("mandatory_cognitive_exact_percent") or {}
    competency_quotas = payload.get("mandatory_competency_exact_percent") or {}

    for index, target in enumerate(cognitive):
        if target.key not in allowed_cognitive:
            return False, f"cognitive_targets[{index}]/key"
        approved = cognitive_quotas.get(target.key)
        if approved is not None:
            if target.exact_percent is None:
                return False, f"cognitive_targets[{index}]/exact_percent"
            if abs(target.exact_percent - float(approved)) > 0.01:
                return False, f"cognitive_targets[{index}]/exact_percent"
        if target.min_percent is not None and target.max_percent is not None:
            if target.min_percent > target.max_percent:
                return False, f"cognitive_targets[{index}]/range"

    for index, target in enumerate(competency):
        if target.key not in allowed_competency:
            return False, f"competency_targets[{index}]/key"
        approved = competency_quotas.get(target.key)
        if approved is not None:
            if target.exact_percent is None:
                return False, f"competency_targets[{index}]/exact_percent"
            if abs(target.exact_percent - float(approved)) > 0.01:
                return False, f"competency_targets[{index}]/exact_percent"

    return True, None
