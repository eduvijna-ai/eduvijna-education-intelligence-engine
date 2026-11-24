"""D16-07..D16-10 versioned deterministic adaptive policy."""

from __future__ import annotations

from dataclasses import dataclass

from app.adaptive_remediation.contracts import EvidenceObservation, RemediationTarget
from app.adaptive_remediation.enums import (
    CorrectionPatternKind,
    EvidenceSupportLevel,
    RemediationStrategyKind,
    RemediationVerdict,
)
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle

POLICY_VERSION = "d16-adaptive-policy-v1"
POLICY_RATIONALE = (
    "Deterministic heuristic prioritization by evidence support, learning goal alignment "
    "and prerequisite dependency hints. No IRT/BKT/clinical diagnostic claims."
)
POLICY_LIMITATIONS = (
    "Thresholds: SUPPORTED>=40, RECURRENT>=35, SINGLE>=20, INSUFFICIENT>=5, UNKNOWN=0 score. "
    "Cold-start and UNKNOWN never imply mastery. Target +10, learning goal +5 tie boosts."
)


@dataclass(frozen=True, slots=True)
class PrioritizedConcept:
    concept_code: str
    score: int
    support: EvidenceSupportLevel


_SUPPORT_SCORE = {
    EvidenceSupportLevel.SUPPORTED: 40,
    EvidenceSupportLevel.RECURRENT: 35,
    EvidenceSupportLevel.SINGLE_OBSERVATION: 20,
    EvidenceSupportLevel.INSUFFICIENT: 5,
    EvidenceSupportLevel.UNKNOWN: 0,
}

_PATTERN_STRATEGY: dict[CorrectionPatternKind, RemediationStrategyKind] = {
    CorrectionPatternKind.CONCEPTUAL: RemediationStrategyKind.CONCEPT_REVIEW,
    CorrectionPatternKind.FORMULA: RemediationStrategyKind.FORMULA_FOCUS,
    CorrectionPatternKind.CALCULATION: RemediationStrategyKind.CALCULATION_DRILL,
    CorrectionPatternKind.APPLICATION: RemediationStrategyKind.APPLICATION_PRACTICE,
    CorrectionPatternKind.REASONING: RemediationStrategyKind.REASONING_PRACTICE,
    CorrectionPatternKind.MISCONCEPTION: RemediationStrategyKind.MISCONCEPTION_REPAIR,
}


def rank_concept_needs(
    bundle: NormalizedEvidenceBundle,
    *,
    target_concept_code: str,
    learning_goal_codes: tuple[str, ...] = (),
) -> list[PrioritizedConcept]:
    by_concept: dict[str, list[EvidenceObservation]] = {}
    for obs in bundle.accepted:
        by_concept.setdefault(obs.concept_code, []).append(obs)

    ranked: list[PrioritizedConcept] = []
    for concept, obs_list in sorted(by_concept.items()):
        best = max(obs_list, key=lambda o: _SUPPORT_SCORE.get(o.support_level, 0))
        score = _SUPPORT_SCORE.get(best.support_level, 0)
        if best.support_level in (EvidenceSupportLevel.UNKNOWN, EvidenceSupportLevel.INSUFFICIENT):
            continue
        if concept == target_concept_code:
            score += 10
        if concept in learning_goal_codes:
            score += 5
        ranked.append(
            PrioritizedConcept(concept_code=concept, score=score, support=best.support_level)
        )

    ranked.sort(key=lambda r: (-r.score, r.concept_code))
    return ranked


def map_strategy(
    obs: EvidenceObservation,
    *,
    prerequisite_of: str | None = None,
) -> RemediationTarget:
    if obs.support_level in (EvidenceSupportLevel.UNKNOWN, EvidenceSupportLevel.INSUFFICIENT):
        return RemediationTarget(
            concept_code=obs.concept_code,
            strategy=RemediationStrategyKind.ASSESSMENT_NEED,
            rationale="Insufficient evidence; diagnostic assessment need only.",
            evidence_support=obs.support_level,
            prerequisite_of=prerequisite_of,
        )
    strategy = _PATTERN_STRATEGY.get(obs.pattern_kind, RemediationStrategyKind.REVIEW_REQUIRED)
    recurrent = obs.support_level == EvidenceSupportLevel.RECURRENT
    rationale = (
        f"Recurrent {obs.pattern_kind.value} pattern with {obs.support_level.value} support."
        if recurrent
        else f"Single {obs.pattern_kind.value} observation; confirm before mastery claim."
    )
    return RemediationTarget(
        concept_code=obs.concept_code,
        strategy=strategy,
        rationale=rationale,
        evidence_support=obs.support_level,
        prerequisite_of=prerequisite_of,
    )


def policy_verdict_for_cold_start(cold_start: bool) -> RemediationVerdict:
    if cold_start:
        return RemediationVerdict.REVIEW_REQUIRED
    return RemediationVerdict.DIAGNOSTIC_PLAN
