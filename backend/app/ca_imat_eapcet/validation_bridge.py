from __future__ import annotations

from app.ca_imat_eapcet.enums import PlanVerdict


def day6_bridge_status() -> dict[str, object]:
    """D14-28: Day6 validator integration hook (not fully wired in candidate 1)."""

    return {
        "wired": False,
        "verdict": PlanVerdict.REVIEW_REQUIRED.value,
        "note": "Reuse path reserved; descriptive items only when applicable",
    }


def day9_day10_bridge_status() -> dict[str, object]:
    return {
        "day9_distractors": {"wired": False, "verdict": PlanVerdict.REVIEW_REQUIRED.value},
        "day10_distribution": {"wired": False, "verdict": PlanVerdict.REVIEW_REQUIRED.value},
    }