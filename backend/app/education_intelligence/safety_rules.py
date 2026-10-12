from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.registry_versions import RegistryVersionNotFound
from app.models.education_intelligence import PolicyRegistryEntry

V1_SAFETY_RULES_VERSION = "safety-rules-v1.0"

DEFAULT_SAFETY_RULES: list[dict[str, Any]] = [
    {
        "rule_code": "SAFE-BLOCK-001",
        "match_type": "substring",
        "pattern": "kill yourself",
        "severity": "safety",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-BLOCK-002",
        "match_type": "substring",
        "pattern": "unnecessary ssn",
        "severity": "safety",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-BLOCK-003",
        "match_type": "substring",
        "pattern": "unsafe lab experiment",
        "severity": "safety",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-REVIEW-001",
        "match_type": "substring",
        "pattern": "demeaning stereotype",
        "severity": "safety",
        "blocking": False,
        "review_required": True,
    },
]


@dataclass
class SafetyRulePack:
    version: str = V1_SAFETY_RULES_VERSION
    policy_version: str = ""
    rules: list[dict[str, Any]] = field(default_factory=list)
    found: bool = True


def _safety_payload(policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rules = policy_payload.get("safety_rules")
    if isinstance(rules, list) and rules:
        return rules
    return DEFAULT_SAFETY_RULES


def _pack_from_row(row: PolicyRegistryEntry) -> SafetyRulePack:
    payload = row.payload_json
    return SafetyRulePack(
        version=str(payload.get("safety_rules_version", V1_SAFETY_RULES_VERSION)),
        policy_version=row.version,
        rules=_safety_payload(payload),
        found=True,
    )


def load_safety_rule_pack(
    session: Session | None,
    policy_version: str,
    *,
    safety_rules_version: str | None = None,
) -> SafetyRulePack:
    if session is None:
        if safety_rules_version:
            raise RegistryVersionNotFound("safety_rules", safety_rules_version)
        return SafetyRulePack(policy_version=policy_version, rules=list(DEFAULT_SAFETY_RULES))
    if safety_rules_version:
        row = session.scalar(
            select(PolicyRegistryEntry).where(
                PolicyRegistryEntry.version == policy_version,
            )
        )
        if row is None:
            raise RegistryVersionNotFound("policy", policy_version)
        actual = row.payload_json.get("safety_rules_version")
        if actual != safety_rules_version:
            raise RegistryVersionNotFound("safety_rules", safety_rules_version)
        return _pack_from_row(row)
    row = session.scalar(
        select(PolicyRegistryEntry)
        .where(PolicyRegistryEntry.registry_key == "v1")
        .order_by(PolicyRegistryEntry.created_at.desc())
        .limit(1)
    )
    if row is None:
        return SafetyRulePack(policy_version=policy_version, rules=list(DEFAULT_SAFETY_RULES))
    if policy_version and row.version != policy_version:
        historical = session.scalar(
            select(PolicyRegistryEntry).where(PolicyRegistryEntry.version == policy_version)
        )
        if historical is None:
            raise RegistryVersionNotFound("policy", policy_version)
        return _pack_from_row(historical)
    return _pack_from_row(row)


def seed_safety_rules_in_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("safety_rules_version", V1_SAFETY_RULES_VERSION)
    payload.setdefault("safety_rules", DEFAULT_SAFETY_RULES)
    return payload
