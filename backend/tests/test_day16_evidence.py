from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import CorrectionPatternKind, EvidenceSupportLevel
from app.adaptive_remediation.evidence import normalize_observations


def _obs(obs_id: str, concept: str = "c1", version: str = "v1") -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=obs_id,
        concept_code=concept,
        pattern_kind=CorrectionPatternKind.CONCEPTUAL,
        support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
        curriculum_version_code=version,
    )


def test_reject_duplicate_and_cross_version() -> None:
    bundle = normalize_observations(
        (_obs("a"), _obs("a"), _obs("b", version="v2")), curriculum_version_code="v1"
    )
    assert len(bundle.accepted) == 1
    assert "DUPLICATE_OBSERVATION_ID" in bundle.issue_codes
    assert "CROSS_VERSION_OBSERVATION" in bundle.issue_codes
