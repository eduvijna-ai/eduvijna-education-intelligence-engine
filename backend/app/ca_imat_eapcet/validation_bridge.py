from __future__ import annotations

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.enums import PlanVerdict
from app.education_intelligence.service import EducationIntelligenceValidationService


def day6_bridge_status(session: Session | None = None) -> dict[str, object]:
    """D14-28: Day6 validator availability (full persisted wire NOT_READY without Question rows)."""

    _ = session
    _ = EducationIntelligenceValidationService  # import boundary present
    return {
        "wired_to_persisted_questions": False,
        "verdict": PlanVerdict.NOT_READY.value,
        "note": "Use cuet_validation_bridge pattern when Day14 persisted pool lands",
    }


def day9_day10_bridge_status() -> dict[str, object]:
    return {
        "day9_distractors": {"wired": False, "verdict": PlanVerdict.NOT_READY.value},
        "day10_distribution": {"wired": False, "verdict": PlanVerdict.NOT_READY.value},
    }


def day7_day8_bridge_status() -> dict[str, object]:
    return {
        "day7_anythingllm_adapter": {"wired": False, "verdict": PlanVerdict.NOT_READY.value},
        "day8_orchestration": {"wired": False, "verdict": PlanVerdict.NOT_READY.value},
        "direct_provider_sdk": False,
    }