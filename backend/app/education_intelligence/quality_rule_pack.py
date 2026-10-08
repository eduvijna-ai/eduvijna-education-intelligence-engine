from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.enums import ValidationSeverity
from app.models.education_intelligence import EducationalQualityRulePack

V1_QUALITY_PACK_VERSION = "quality-v1.0"

DEFAULT_QUALITY_RULES: list[dict[str, Any]] = [
    {
        "rule_code": "QUAL-ALIGN-001",
        "check": "non_empty_stem",
        "severity": ValidationSeverity.MANDATORY.value,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-CLAR-001",
        "check": "single_choice_min_options",
        "severity": ValidationSeverity.MANDATORY.value,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-ANS-001",
        "check": "answer_metadata_present",
        "severity": ValidationSeverity.MANDATORY.value,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-EXPL-001",
        "check": "explanation_when_required",
        "severity": ValidationSeverity.MANDATORY.value,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-TRICK-001",
        "check": "avoid_trick_wording",
        "severity": ValidationSeverity.ADVISORY.value,
        "blocking": False,
    },
]


@dataclass
class QualityRulePack:
    version: str = V1_QUALITY_PACK_VERSION
    rules: list[dict[str, Any]] = field(default_factory=list)


def seed_quality_rule_pack(session: Session) -> QualityRulePack:
    existing = session.scalar(
        select(EducationalQualityRulePack).where(
            EducationalQualityRulePack.pack_key == "v1",
            EducationalQualityRulePack.version == V1_QUALITY_PACK_VERSION,
            EducationalQualityRulePack.status == "active",
        )
    )
    if existing is None:
        session.add(
            EducationalQualityRulePack(
                pack_key="v1",
                version=V1_QUALITY_PACK_VERSION,
                status="active",
                rules_json=DEFAULT_QUALITY_RULES,
                description="Day 6 default educational quality rules",
            )
        )
        session.flush()
    return load_quality_rule_pack(session)


def load_quality_rule_pack(session: Session | None) -> QualityRulePack:
    if session is None:
        return QualityRulePack(rules=list(DEFAULT_QUALITY_RULES))
    row = session.scalar(
        select(EducationalQualityRulePack)
        .where(EducationalQualityRulePack.pack_key == "v1")
        .order_by(EducationalQualityRulePack.created_at.desc())
        .limit(1)
    )
    if row is None:
        return seed_quality_rule_pack(session)
    return QualityRulePack(version=row.version, rules=list(row.rules_json))
