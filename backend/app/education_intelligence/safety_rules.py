from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import PolicyRegistryEntry

V1_SAFETY_RULES_VERSION = "safety-rules-v1.0"

DEFAULT_SAFETY_RULES: list[dict[str, Any]] = [
    {
        "rule_code": "SAFE-BLOCK-001",
        "match_type": "substring",
        "pattern": "kill yourself",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-BLOCK-002",
        "match_type": "substring",
        "pattern": "unnecessary ssn",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-BLOCK-003",
        "match_type": "substring",
        "pattern": "unsafe lab experiment",
        "blocking": True,
    },
    {
        "rule_code": "SAFE-REVIEW-001",
        "match_type": "substring",
        "pattern": "demeaning stereotype",
        "blocking": False,
        "review_required": True,
    },
]


@dataclass
class SafetyRulePack:
    version: str = V1_SAFETY_RULES_VERSION
    policy_version: str = ""
    rules: list[dict[str, Any]] = field(default_factory=list)


def _safety_payload(policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rules = policy_payload.get("safety_rules")
    if isinstance(rules, list) and rules:
        return rules
    return DEFAULT_SAFETY_RULES


def load_safety_rule_pack(session: Session | None, policy_version: str) -> SafetyRulePack:
    if session is None:
        return SafetyRulePack(policy_version=policy_version, rules=list(DEFAULT_SAFETY_RULES))
    row = session.scalar(
        select(PolicyRegistryEntry)
        .where(PolicyRegistryEntry.registry_key == "v1")
        .order_by(PolicyRegistryEntry.created_at.desc())
        .limit(1)
    )
    if row is None:
        return SafetyRulePack(policy_version=policy_version, rules=list(DEFAULT_SAFETY_RULES))
    return SafetyRulePack(
        version=row.payload_json.get("safety_rules_version", V1_SAFETY_RULES_VERSION),
        policy_version=row.version,
        rules=_safety_payload(row.payload_json),
    )


def seed_safety_rules_in_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("safety_rules_version", V1_SAFETY_RULES_VERSION)
    payload.setdefault("safety_rules", DEFAULT_SAFETY_RULES)
    return payload
