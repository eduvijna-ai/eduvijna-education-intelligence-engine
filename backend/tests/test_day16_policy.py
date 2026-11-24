from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import (
    CorrectionPatternKind,
    EvidenceSupportLevel,
    RemediationStrategyKind,
)
from app.adaptive_remediation.evidence import normalize_observations
from app.adaptive_remediation.policy import map_strategy, rank_concept_needs


def test_rank_deterministic_tiebreak() -> None:
    observations = (
        EvidenceObservation(
            observation_id="1",
            concept_code="b-concept",
            pattern_kind=CorrectionPatternKind.CALCULATION,
            support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
            curriculum_version_code="v1",
        ),
        EvidenceObservation(
            observation_id="2",
            concept_code="a-concept",
            pattern_kind=CorrectionPatternKind.CALCULATION,
            support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
            curriculum_version_code="v1",
        ),
    )
    bundle = normalize_observations(observations, curriculum_version_code="v1")
    ranked = rank_concept_needs(bundle, target_concept_code="a-concept")
    assert [r.concept_code for r in ranked][0] == "a-concept"


def test_unknown_maps_to_assessment_need() -> None:
    obs = EvidenceObservation(
        observation_id="u",
        concept_code="x",
        pattern_kind=CorrectionPatternKind.CONCEPTUAL,
        support_level=EvidenceSupportLevel.UNKNOWN,
        curriculum_version_code="v1",
    )
    target = map_strategy(obs)
    assert target.strategy is RemediationStrategyKind.ASSESSMENT_NEED
