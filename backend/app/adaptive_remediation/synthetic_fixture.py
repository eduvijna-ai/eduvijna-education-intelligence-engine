"""Fixed authoritative synthetic fixture constants — single allowed diagnostic envelope."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.adaptive_remediation.contracts import (
    CurriculumScopeRef,
    EvidenceObservation,
    LearnerHistoryRef,
)
from app.adaptive_remediation.enums import CorrectionPatternKind, EvidenceSupportLevel

AUTHORITATIVE_AS_OF = date(2026, 11, 24)
GRAPH_ASSEMBLED_AT = "2026-11-24T00:00:00+00:00"
SYNTHETIC_CATALOGUE_VERSION = "d16-catalogue-v1"
AUTHORITATIVE_POLICY_VERSION = "d16-adaptive-policy-v1"
AUTHORITATIVE_EVIDENCE_POLICY = "d16-evidence-v1"

AUTHORITATIVE_CURRICULUM = CurriculumScopeRef(
    curriculum_pack_code="d16-synth-physics",
    curriculum_version_code="d16-synth-physics-v1",
    subject_code="physics",
    grade_year_code="grade-11",
)

AUTHORITATIVE_TARGET_CONCEPT = "friction-formula-selection"

ALLOWED_GRAPH_SCOPE_VERSION = "synthetic-d16-physics-v1"
ALLOWED_GRAPH_SNAPSHOT_ID = "d16-friction-snapshot"
ALLOWED_GRAPH_VERSION = "d16-synth-physics-v1"

ALLOWED_CONCEPT_CODES = frozenset(
    {
        "newton-laws",
        "normal-force",
        "friction-applications",
        "friction-formula-selection",
    }
)

AUTHORITATIVE_REQUESTED_COUNT = 10

INTERNAL_HISTORY = LearnerHistoryRef(
    history_slot="synthetic-slot-a",
    recent_concept_codes=("friction-applications",),
    excluded_question_ids=("d16-q-nl-01",),
)

INTERNAL_OBSERVATIONS: tuple[EvidenceObservation, ...] = (
    EvidenceObservation(
        observation_id="d16-obs-1",
        concept_code="friction-formula-selection",
        pattern_kind=CorrectionPatternKind.FORMULA,
        support_level=EvidenceSupportLevel.RECURRENT,
        source_revision_id="d16-synth-source-v1",
        source_locator="internal/synthetic/friction-formula",
        observed_at=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
        curriculum_version_code="d16-synth-physics-v1",
        uncertainty_note="Illustrative synthetic observation only.",
    ),
    EvidenceObservation(
        observation_id="d16-obs-2",
        concept_code="friction-applications",
        pattern_kind=CorrectionPatternKind.APPLICATION,
        support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
        source_revision_id="d16-synth-source-v1",
        source_locator="internal/synthetic/friction-application",
        observed_at=datetime(2026, 11, 21, 12, 0, tzinfo=UTC),
        policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
        curriculum_version_code="d16-synth-physics-v1",
    ),
    EvidenceObservation(
        observation_id="d16-obs-3",
        concept_code="normal-force",
        pattern_kind=CorrectionPatternKind.CONCEPTUAL,
        support_level=EvidenceSupportLevel.INSUFFICIENT,
        source_revision_id="d16-synth-source-v1",
        source_locator="internal/synthetic/normal-force",
        observed_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
        curriculum_version_code="d16-synth-physics-v1",
    ),
)

AUTHORITATIVE_PLAN_ID = "d16-plan-authoritative-friction-v1"
