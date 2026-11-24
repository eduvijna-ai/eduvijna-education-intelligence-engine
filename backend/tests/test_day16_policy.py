from datetime import UTC, date, datetime

from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import (
    CorrectionPatternKind,
    EvidenceSupportLevel,
    RemediationStrategyKind,
)
from app.adaptive_remediation.evidence import normalize_observations
from app.adaptive_remediation.policy import POLICY_LIMITATIONS, map_strategy, rank_concept_needs
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_CONCEPT_CODES,
    AUTHORITATIVE_EVIDENCE_POLICY,
    AUTHORITATIVE_SOURCE_REVISION_ID,
)


def test_rank_deterministic_tiebreak() -> None:
    observations = (
        EvidenceObservation(
            observation_id="1",
            concept_code="friction-applications",
            pattern_kind=CorrectionPatternKind.CALCULATION,
            support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
            source_revision_id=AUTHORITATIVE_SOURCE_REVISION_ID,
            source_locator="internal/synthetic/policy-rank-1",
            observed_at=datetime(2026, 11, 20, tzinfo=UTC),
            policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
            curriculum_version_code="d16-synth-physics-v1",
        ),
        EvidenceObservation(
            observation_id="2",
            concept_code="friction-formula-selection",
            pattern_kind=CorrectionPatternKind.CALCULATION,
            support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
            source_revision_id=AUTHORITATIVE_SOURCE_REVISION_ID,
            source_locator="internal/synthetic/policy-rank-2",
            observed_at=datetime(2026, 11, 21, tzinfo=UTC),
            policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
            curriculum_version_code="d16-synth-physics-v1",
        ),
    )
    bundle = normalize_observations(
        observations,
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=date(2026, 11, 24),
        evidence_policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
    )
    ranked = rank_concept_needs(bundle, target_concept_code="friction-formula-selection")
    assert ranked[0].concept_code == "friction-formula-selection"


def test_unknown_maps_to_assessment_need() -> None:
    obs = EvidenceObservation(
        observation_id="u",
        concept_code="friction-formula-selection",
        pattern_kind=CorrectionPatternKind.CONCEPTUAL,
        support_level=EvidenceSupportLevel.UNKNOWN,
        curriculum_version_code="d16-synth-physics-v1",
    )
    target = map_strategy(obs)
    assert target.strategy is RemediationStrategyKind.ASSESSMENT_NEED


def test_policy_limitations_documented() -> None:
    assert "UNKNOWN=0" in POLICY_LIMITATIONS