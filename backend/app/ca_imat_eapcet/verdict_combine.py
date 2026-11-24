from __future__ import annotations

from app.ca_imat_eapcet.enums import PlanVerdict

_PRIORITY: tuple[PlanVerdict, ...] = (
    PlanVerdict.FAIL,
    PlanVerdict.SOURCE_PENDING,
    PlanVerdict.OFFICIAL_NOT_VERIFIED,
    PlanVerdict.NOT_READY,
    PlanVerdict.SHORTAGE,
    PlanVerdict.REVIEW_REQUIRED,
    PlanVerdict.PASS,
)


def combine_verdicts(*verdicts: PlanVerdict) -> PlanVerdict:
    if not verdicts:
        return PlanVerdict.FAIL
    best = len(_PRIORITY)
    chosen = PlanVerdict.FAIL
    for v in verdicts:
        try:
            rank = _PRIORITY.index(v)
        except ValueError:
            rank = 0
        if rank < best:
            best = rank
            chosen = v
    return chosen