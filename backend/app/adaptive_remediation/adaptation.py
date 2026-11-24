"""D16-24..D16-28 adaptation cycle decisions (synthetic only)."""

from __future__ import annotations

from datetime import date, timedelta

from app.adaptive_remediation.enums import AdaptationDecision, EvidenceSupportLevel
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle

MAX_PRACTICE_REPETITIONS = 3
SPACING_DAYS = (1, 3, 7)


def decide_adaptation(
    bundle: NormalizedEvidenceBundle,
    *,
    target_concept_code: str,
    prior_cycle_count: int,
    practice_completed: bool,
) -> tuple[AdaptationDecision, str]:
    if prior_cycle_count >= MAX_PRACTICE_REPETITIONS:
        return AdaptationDecision.STOP, "Maximum synthetic practice repetitions reached."
    if not bundle.accepted:
        return AdaptationDecision.INSUFFICIENT_EVIDENCE, "No accepted evidence; assessment need."
    target = [o for o in bundle.accepted if o.concept_code == target_concept_code]
    if not target:
        return AdaptationDecision.REVIEW, "Target concept lacks mapped observations."
    best = max(target, key=lambda o: o.support_level)
    if best.support_level == EvidenceSupportLevel.UNKNOWN:
        return AdaptationDecision.INSUFFICIENT_EVIDENCE, "Unknown support; cannot infer mastery."
    if best.support_level == EvidenceSupportLevel.SINGLE_OBSERVATION:
        return AdaptationDecision.REVIEW, "Single observation; cannot claim improvement."
    if practice_completed and best.support_level == EvidenceSupportLevel.SUPPORTED:
        return AdaptationDecision.IMPROVE, "Supported evidence after practice; illustrative only."
    if practice_completed:
        return (
            AdaptationDecision.CONTINUE,
            "Practice completed without sufficient support for mastery.",
        )
    return (
        AdaptationDecision.CONTINUE,
        "Continue synthetic plan; completion alone does not advance.",
    )


def propose_spacing(as_of: date, cycle_index: int) -> date | None:
    if cycle_index >= len(SPACING_DAYS):
        return None
    return as_of + timedelta(days=SPACING_DAYS[cycle_index])
