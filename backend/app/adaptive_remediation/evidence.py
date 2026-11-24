"""D16-05 evidence normalization and rejection rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import EvidenceSupportLevel


@dataclass(frozen=True, slots=True)
class NormalizedEvidenceBundle:
    accepted: tuple[EvidenceObservation, ...]
    rejected_ids: tuple[str, ...]
    issue_codes: tuple[str, ...]


def normalize_observations(
    observations: tuple[EvidenceObservation, ...],
    *,
    curriculum_version_code: str,
) -> NormalizedEvidenceBundle:
    accepted: list[EvidenceObservation] = []
    rejected: list[str] = []
    issues: list[str] = []
    seen_ids: set[str] = set()
    concept_support: dict[str, set[EvidenceSupportLevel]] = {}

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
        if not obs.concept_code:
            rejected.append(obs.observation_id)
            issues.append("UNMAPPED_CONCEPT")
            continue

        seen_ids.add(obs.observation_id)
        prior = concept_support.setdefault(obs.concept_code, set())
        if (
            obs.support_level in prior
            and obs.support_level != EvidenceSupportLevel.SINGLE_OBSERVATION
        ):
            rejected.append(obs.observation_id)
            issues.append("CONTRADICTORY_SUPPORT_LEVEL")
            continue
        prior.add(obs.support_level)
        accepted.append(obs)

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
    return all(o.support_level == EvidenceSupportLevel.UNKNOWN for o in target_obs)
