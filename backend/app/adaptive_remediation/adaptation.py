"""D16-24..D16-28 adaptation cycle decisions (synthetic only)."""

from __future__ import annotations

from datetime import date, timedelta

from app.adaptive_remediation.enums import AdaptationDecision, EvidenceSupportLevel
from app.adaptive_remediation.evidence import (
    NormalizedEvidenceBundle,
    _support_rank,
    best_target_evidence,
)

MAX_PRACTICE_REPETITIONS = 3
SPACING_DAYS = (1, 3, 7)


def decide_adaptation(
    bundle: NormalizedEvidenceBundle,
    *,
    target_concept_code: str,
    prior_cycle_count: int,
    practice_completed: bool,
    pre_practice_rank: int | None = None,
) -> tuple[AdaptationDecision, str]:
    if prior_cycle_count < 0:
        return AdaptationDecision.STOP, "Invalid negative cycle index."
    if prior_cycle_count >= MAX_PRACTICE_REPETITIONS:
        return AdaptationDecision.STOP, "Maximum synthetic practice repetitions reached."
    if not bundle.accepted:
        return AdaptationDecision.INSUFFICIENT_EVIDENCE, "No accepted evidence; assessment need."

    best = best_target_evidence(bundle, target_concept_code)
    if best is None:
        return AdaptationDecision.REVIEW, "Target concept lacks mapped observations."

    rank = _support_rank(best.support_level)
    if best.support_level == EvidenceSupportLevel.UNKNOWN:
        return AdaptationDecision.INSUFFICIENT_EVIDENCE, "Unknown support; cannot infer mastery."
    if practice_completed:
        if pre_practice_rank is not None and rank < pre_practice_rank:
            return (
                AdaptationDecision.REGRESS,
                "Illustrative regress; lower support vs pre-practice.",
            )
        if pre_practice_rank is not None and rank > pre_practice_rank:
            return (
                AdaptationDecision.IMPROVE,
                "Illustrative improve after distinct post-practice evidence.",
            )
        if best.support_level in (
            EvidenceSupportLevel.INSUFFICIENT,
            EvidenceSupportLevel.SINGLE_OBSERVATION,
        ):
            return AdaptationDecision.REVIEW, "Insufficient or single observation; no mastery claim."
        return (
            AdaptationDecision.CONTINUE,
            "Practice completed without independent post-practice evidence comparison.",
        )

    if best.support_level in (
        EvidenceSupportLevel.INSUFFICIENT,
        EvidenceSupportLevel.SINGLE_OBSERVATION,
    ):
        return AdaptationDecision.REVIEW, "Insufficient or single observation; no mastery claim."

    return (
        AdaptationDecision.CONTINUE,
        "Continue synthetic plan; completion alone does not advance.",
    )


def propose_spacing(as_of: date, cycle_index: int) -> date | None:
    if cycle_index < 0 or cycle_index >= len(SPACING_DAYS):
        return None
    return as_of + timedelta(days=SPACING_DAYS[cycle_index])
