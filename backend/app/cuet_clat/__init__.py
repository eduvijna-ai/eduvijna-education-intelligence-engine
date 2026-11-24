"""CUET UG / CLAT UG examination intelligence (Day 13)."""

from app.cuet_clat.authority import resolve_clat_authority, resolve_cuet_authority
from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.contracts import (
    ClatPaperPlanRequest,
    ClatPaperPlanResult,
    CuetPracticeRequest,
    CuetPracticeResult,
    CuetSingleTestRequest,
    CuetSingleTestResult,
)
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, PlanVerdict
from app.cuet_clat.governance import build_day13_governance_record
from app.cuet_clat.practice_service import CuetPracticeService

__all__ = [
    "ClatPaperPlanRequest",
    "ClatPaperPlanResult",
    "ClatPaperPlanner",
    "CuetClatProfileKind",
    "CuetClatSourceTrustMode",
    "CuetPracticeRequest",
    "CuetPracticeResult",
    "CuetPracticeService",
    "CuetSingleTestRequest",
    "CuetSingleTestResult",
    "PlanVerdict",
    "build_day13_governance_record",
    "resolve_clat_authority",
    "resolve_cuet_authority",
]