from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.contracts import InstitutionPolicyOverride, PolicyRuleConfig
from app.education_intelligence.enums import PolicyAuthorityTier, ValidationSeverity
from app.education_intelligence.safety_rules import seed_safety_rules_in_policy_payload
from app.models.education_intelligence import PolicyRegistryEntry

V1_POLICY_VERSION = "education-policy-v1.0"

DEFAULT_GLOBAL_RULES: list[PolicyRuleConfig] = [
    PolicyRuleConfig(
        policy_key="safety.no_unsafe_instruction",
        authority_tier=PolicyAuthorityTier.GLOBAL.value,
        scope_code="global",
        rule_code="POL-SAFETY-001",
        severity=ValidationSeverity.SAFETY,
        blocking=True,
        prohibits=["unsafe_instruction"],
    ),
    PolicyRuleConfig(
        policy_key="quality.explanation_when_required",
        authority_tier=PolicyAuthorityTier.GLOBAL.value,
        scope_code="global",
        rule_code="POL-QUALITY-001",
        severity=ValidationSeverity.MANDATORY,
        blocking=True,
        requires=["explanation_present"],
    ),
]

DEFAULT_BOARD_RULES: list[PolicyRuleConfig] = [
    PolicyRuleConfig(
        policy_key="board.official_competency_integrity",
        authority_tier=PolicyAuthorityTier.COUNTRY_BOARD.value,
        scope_code="cbse",
        rule_code="POL-CBSE-COMP-001",
        severity=ValidationSeverity.MANDATORY,
        blocking=True,
        requires=["official_competency_evidence"],
    ),
]


@dataclass
class PolicyRegistry:
    version: str = V1_POLICY_VERSION
    rules: list[PolicyRuleConfig] = field(default_factory=list)
    institution_overrides: list[InstitutionPolicyOverride] = field(default_factory=list)

    def rules_for_scope(
        self,
        *,
        board_code: str | None,
        institution_id: str | None,
    ) -> list[PolicyRuleConfig]:
        applicable: list[PolicyRuleConfig] = []
        for rule in self.rules:
            if rule.authority_tier == PolicyAuthorityTier.GLOBAL.value:
                applicable.append(rule)
            elif (
                rule.authority_tier == PolicyAuthorityTier.COUNTRY_BOARD.value
                and board_code
                and rule.scope_code == board_code
            ):
                applicable.append(rule)
        if institution_id:
            override_keys = {
                o.policy_key: o
                for o in self.institution_overrides
                if o.institution_id == institution_id
            }
            filtered: list[PolicyRuleConfig] = []
            for rule in applicable:
                if rule.policy_key in override_keys:
                    ov = override_keys[rule.policy_key]
                    if _override_weakens(rule, ov):
                        filtered.append(rule)
                        continue
                    merged = rule.model_copy()
                    merged.value = {**rule.value, **ov.value}
                    filtered.append(merged)
                else:
                    filtered.append(rule)
            return _sort_by_authority(filtered)
        return _sort_by_authority(applicable)


def _sort_by_authority(rules: list[PolicyRuleConfig]) -> list[PolicyRuleConfig]:
    order = {
        PolicyAuthorityTier.GLOBAL.value: 0,
        PolicyAuthorityTier.COUNTRY_BOARD.value: 1,
        PolicyAuthorityTier.INSTITUTION.value: 2,
        PolicyAuthorityTier.TEACHER.value: 3,
    }
    return sorted(rules, key=lambda r: order.get(r.authority_tier, 99))


def _override_weakens(rule: PolicyRuleConfig, override: InstitutionPolicyOverride) -> bool:
    if override.value.get("disable_blocking"):
        return True
    if rule.prohibits and override.value.get("allow_prohibited"):
        return True
    return False


def seed_policy_registry(session: Session) -> PolicyRegistry:
    payload = seed_safety_rules_in_policy_payload(
        {
            "rules": [
                r.model_dump(mode="json") for r in DEFAULT_GLOBAL_RULES + DEFAULT_BOARD_RULES
            ],
            "institution_overrides": [],
        }
    )
    existing = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == "v1",
            PolicyRegistryEntry.version == V1_POLICY_VERSION,
            PolicyRegistryEntry.status == "active",
        )
    )
    if existing is None:
        session.add(
            PolicyRegistryEntry(
                registry_key="v1",
                version=V1_POLICY_VERSION,
                status="active",
                payload_json=payload,
            )
        )
        session.flush()
    return _from_payload(V1_POLICY_VERSION, payload)


def load_policy_registry(
    session: Session | None,
    institution_overrides: list[InstitutionPolicyOverride] | None = None,
) -> PolicyRegistry:
    if session is None:
        reg = PolicyRegistry(rules=DEFAULT_GLOBAL_RULES + DEFAULT_BOARD_RULES)
        if institution_overrides:
            reg.institution_overrides = institution_overrides
        return reg
    row = session.scalar(
        select(PolicyRegistryEntry)
        .where(PolicyRegistryEntry.registry_key == "v1")
        .order_by(PolicyRegistryEntry.created_at.desc())
        .limit(1)
    )
    if row is None:
        reg = seed_policy_registry(session)
    else:
        reg = _from_payload(row.version, row.payload_json)
    if institution_overrides:
        reg.institution_overrides = institution_overrides
    return reg


def _from_payload(version: str, payload: dict[str, Any]) -> PolicyRegistry:
    rules = [PolicyRuleConfig.model_validate(r) for r in payload.get("rules", [])]
    overrides = [
        InstitutionPolicyOverride.model_validate(o)
        for o in payload.get("institution_overrides", [])
    ]
    return PolicyRegistry(version=version, rules=rules, institution_overrides=overrides)
