from datetime import UTC, date, datetime

from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import CorrectionPatternKind, EvidenceSupportLevel
from app.adaptive_remediation.evidence import normalize_observations
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_CONCEPT_CODES,
    AUTHORITATIVE_EVIDENCE_POLICY,
)


def _obs(
    obs_id: str,
    concept: str = "friction-formula-selection",
    *,
    support: EvidenceSupportLevel = EvidenceSupportLevel.SINGLE_OBSERVATION,
    version: str = "d16-synth-physics-v1",
    observed_at: datetime | None = None,
) -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=obs_id,
        concept_code=concept,
        pattern_kind=CorrectionPatternKind.CONCEPTUAL,
        support_level=support,
        source_revision_id="d16-synth-source-v1",
        source_locator="internal/synthetic/test-observation",
        curriculum_version_code=version,
        policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
        observed_at=observed_at or datetime(2026, 11, 20, tzinfo=UTC),
    )


def test_reject_duplicate_cross_version_and_unmapped() -> None:
    bundle = normalize_observations(
        (_obs("a"), _obs("a"), _obs("b", version="v2"), _obs("c", concept="bogus")),
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=date(2026, 11, 24),
    )
    assert len(bundle.accepted) == 1
    assert "DUPLICATE_OBSERVATION_ID" in bundle.issue_codes
    assert "CROSS_VERSION_OBSERVATION" in bundle.issue_codes
    assert "UNMAPPED_CONCEPT" in bundle.issue_codes


def test_reject_unknown_plus_supported_conflict() -> None:
    bundle = normalize_observations(
        (
            _obs("1", support=EvidenceSupportLevel.UNKNOWN),
            _obs("2", support=EvidenceSupportLevel.SUPPORTED),
        ),
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=date(2026, 11, 24),
    )
    assert len(bundle.accepted) == 1
    assert "CONTRADICTORY_SUPPORT_LEVEL" in bundle.issue_codes


def test_reject_stale_and_future() -> None:
    stale = normalize_observations(
        (_obs("stale", observed_at=datetime(2020, 1, 1, tzinfo=UTC)),),
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=date(2026, 11, 24),
    )
    future = normalize_observations(
        (_obs("future", observed_at=datetime(2030, 1, 1, tzinfo=UTC)),),
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=date(2026, 11, 24),
    )
    assert "STALE_OBSERVATION" in stale.issue_codes
    assert "FUTURE_OBSERVATION" in future.issue_codes