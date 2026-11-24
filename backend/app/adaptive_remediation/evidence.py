"""D16-05 evidence normalization and rejection rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import EvidenceSupportLevel
from app.adaptive_remediation.synthetic_fixture import AUTHORITATIVE_EVIDENCE_POLICY

_STALE_AFTER = timedelta(days=365)
_FUTURE_GRACE = timedelta(days=1)

_INCOMPATIBLE_SUPPORT = frozenset(
    {
        (EvidenceSupportLevel.UNKNOWN, EvidenceSupportLevel.SUPPORTED),
        (EvidenceSupportLevel.UNKNOWN, EvidenceSupportLevel.RECURRENT),
        (EvidenceSupportLevel.INSUFFICIENT, EvidenceSupportLevel.SUPPORTED),
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedEvidenceBundle:
    accepted: tuple[EvidenceObservation, ...]
    rejected_ids: tuple[str, ...]
    issue_codes: tuple[str, ...]


def normalize_observations(
    observations: tuple[EvidenceObservation, ...],
    *,
    curriculum_version_code: str,
    allowed_concept_codes: frozenset[str],
    as_of: date,
    evidence_policy_version: str = AUTHORITATIVE_EVIDENCE_POLICY,
) -> NormalizedEvidenceBundle:
    accepted: list[EvidenceObservation] = []
    rejected: list[str] = []
    issues: list[str] = []
    seen_ids: set[str] = set()
    concept_levels: dict[str, list[EvidenceSupportLevel]] = {}

    for obs in observations:
        if not obs.observation_id or not obs.observation_id.strip():
            rejected.append(obs.observation_id or "<empty>")
            issues.append("MALFORMED_OBSERVATION_ID")
            continue
        if obs.observation_id in seen_ids:
            rejected.append(obs.observation_id)
            issues.append("DUPLICATE_OBSERVATION_ID")
            continue
        if obs.curriculum_version_code != curriculum_version_code:
            rejected.append(obs.observation_id)
            issues.append("CROSS_VERSION_OBSERVATION")
            continue
        if obs.concept_code not in allowed_concept_codes:
            rejected.append(obs.observation_id)
            issues.append("UNMAPPED_CONCEPT")
            continue
        if obs.policy_version != evidence_policy_version:
            rejected.append(obs.observation_id)
            issues.append("POLICY_VERSION_MISMATCH")
            continue
        if obs.support_level != EvidenceSupportLevel.UNKNOWN and not obs.source_revision_id:
            rejected.append(obs.observation_id)
            issues.append("MISSING_SOURCE_REVISION")
            continue
        if obs.observed_at is not None:
            obs_day = obs.observed_at.date()
            if obs_day > as_of + _FUTURE_GRACE:
                rejected.append(obs.observation_id)
                issues.append("FUTURE_OBSERVATION")
                continue
            if obs_day < as_of - _STALE_AFTER:
                rejected.append(obs.observation_id)
                issues.append("STALE_OBSERVATION")
                continue

        prior_levels = concept_levels.setdefault(obs.concept_code, [])
        for prior in prior_levels:
            pair = (prior, obs.support_level)
            rev = (obs.support_level, prior)
            if pair in _INCOMPATIBLE_SUPPORT or rev in _INCOMPATIBLE_SUPPORT:
                rejected.append(obs.observation_id)
                issues.append("CONTRADICTORY_SUPPORT_LEVEL")
                break
        else:
            seen_ids.add(obs.observation_id)
            prior_levels.append(obs.support_level)
            accepted.append(obs)
            continue

    return NormalizedEvidenceBundle(
        accepted=tuple(accepted),
        rejected_ids=tuple(rejected),
        issue_codes=tuple(dict.fromkeys(issues)),
    )


def cold_start_required(
    bundle: NormalizedEvidenceBundle,
    target_concept_code: str,
) -> bool:
    if not bundle.accepted:
        return True
    target_obs = [o for o in bundle.accepted if o.concept_code == target_concept_code]
    if not target_obs:
        return True
    weakest = min(
        target_obs,
        key=lambda o: _support_rank(o.support_level),
    )
    return weakest.support_level in (
        EvidenceSupportLevel.UNKNOWN,
        EvidenceSupportLevel.INSUFFICIENT,
        EvidenceSupportLevel.SINGLE_OBSERVATION,
    )


def _support_rank(level: EvidenceSupportLevel) -> int:
    order = {
        EvidenceSupportLevel.UNKNOWN: 0,
        EvidenceSupportLevel.INSUFFICIENT: 1,
        EvidenceSupportLevel.SINGLE_OBSERVATION: 2,
        EvidenceSupportLevel.RECURRENT: 3,
        EvidenceSupportLevel.SUPPORTED: 4,
    }
    return order.get(level, -1)


def best_target_evidence(
    bundle: NormalizedEvidenceBundle,
    target_concept_code: str,
) -> EvidenceObservation | None:
    target_obs = [o for o in bundle.accepted if o.concept_code == target_concept_code]
    if not target_obs:
        return None
    return max(target_obs, key=lambda o: _support_rank(o.support_level))
