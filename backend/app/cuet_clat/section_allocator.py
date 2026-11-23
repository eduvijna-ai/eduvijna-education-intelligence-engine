from __future__ import annotations

from dataclasses import dataclass

from app.cuet_clat.constants import CLAT_SECTION_RANGES, CLAT_TOTAL_QUESTIONS
from app.cuet_clat.enums import IssueCode, PlanVerdict


@dataclass(frozen=True, slots=True)
class SectionAllocationOutcome:
    verdict: PlanVerdict
    allocations: dict[str, int]
    issue_codes: tuple[IssueCode, ...]


_SECTION_ORDER: tuple[str, ...] = (
    "english",
    "current_affairs_gk",
    "legal_reasoning",
    "logical_reasoning",
    "quantitative_techniques",
)


def _feasibility_check() -> bool:
    min_total = sum(lo for lo, _ in CLAT_SECTION_RANGES.values())
    max_total = sum(hi for _, hi in CLAT_SECTION_RANGES.values())
    return min_total <= CLAT_TOTAL_QUESTIONS <= max_total


def allocate_clat_sections(
    *,
    section_overrides: dict[str, int] | None = None,
    seed: int = 0,
) -> SectionAllocationOutcome:
    """D13-17/18: deterministic feasible 120-question section split."""

    _ = seed
    if not _feasibility_check():
        return SectionAllocationOutcome(
            verdict=PlanVerdict.FAIL,
            allocations={},
            issue_codes=(IssueCode.CLAT_RANGE_INFEASIBLE,),
        )

    if section_overrides is not None:
        return _validate_overrides(section_overrides)

    counts = {code: CLAT_SECTION_RANGES[code][0] for code in _SECTION_ORDER}
    remaining = CLAT_TOTAL_QUESTIONS - sum(counts.values())
    idx = 0
    while remaining > 0:
        code = _SECTION_ORDER[idx % len(_SECTION_ORDER)]
        lo, hi = CLAT_SECTION_RANGES[code]
        if counts[code] < hi:
            counts[code] += 1
            remaining -= 1
        idx += 1
        if idx > 500:
            break

    if sum(counts.values()) != CLAT_TOTAL_QUESTIONS:
        return SectionAllocationOutcome(
            verdict=PlanVerdict.FAIL,
            allocations=counts,
            issue_codes=(IssueCode.CLAT_RANGE_INFEASIBLE,),
        )

    for code, count in counts.items():
        lo, hi = CLAT_SECTION_RANGES[code]
        if not (lo <= count <= hi):
            return SectionAllocationOutcome(
                verdict=PlanVerdict.FAIL,
                allocations=counts,
                issue_codes=(IssueCode.CLAT_RANGE_INFEASIBLE,),
            )

    return SectionAllocationOutcome(
        verdict=PlanVerdict.PASS,
        allocations=counts,
        issue_codes=(),
    )


def _validate_overrides(overrides: dict[str, int]) -> SectionAllocationOutcome:
    issues: list[IssueCode] = []
    for code, count in overrides.items():
        if code not in CLAT_SECTION_RANGES:
            issues.append(IssueCode.CLAT_SECTION_OVERRIDE_INVALID)
            continue
        lo, hi = CLAT_SECTION_RANGES[code]
        if not (lo <= count <= hi):
            issues.append(IssueCode.CLAT_SECTION_OVERRIDE_INVALID)

    total = sum(overrides.values())
    if total != CLAT_TOTAL_QUESTIONS:
        issues.append(IssueCode.CLAT_COUNT_MISMATCH)

    if issues:
        return SectionAllocationOutcome(
            verdict=PlanVerdict.FAIL,
            allocations=overrides,
            issue_codes=tuple(issues),
        )

    return SectionAllocationOutcome(
        verdict=PlanVerdict.PASS,
        allocations=dict(overrides),
        issue_codes=(),
    )