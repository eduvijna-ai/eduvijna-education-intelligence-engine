from datetime import date

from app.adaptive_remediation.adaptation import decide_adaptation, propose_spacing
from app.adaptive_remediation.contracts import EvidenceObservation
from app.adaptive_remediation.enums import (
    AdaptationDecision,
    CorrectionPatternKind,
    EvidenceSupportLevel,
)
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService


def test_no_improve_without_post_practice_comparison() -> None:
    bundle = NormalizedEvidenceBundle(
        accepted=(
            EvidenceObservation(
                observation_id="1",
                concept_code="friction-formula-selection",
                pattern_kind=CorrectionPatternKind.FORMULA,
                support_level=EvidenceSupportLevel.SUPPORTED,
                source_revision_id="s",
                curriculum_version_code="v1",
            ),
        ),
        rejected_ids=(),
        issue_codes=(),
    )
    decision, _ = decide_adaptation(
        bundle,
        target_concept_code="friction-formula-selection",
        prior_cycle_count=0,
        practice_completed=True,
        pre_practice_rank=4,
    )
    assert decision is AdaptationDecision.CONTINUE


def test_regress_when_support_drops() -> None:
    bundle = NormalizedEvidenceBundle(
        accepted=(
            EvidenceObservation(
                observation_id="1",
                concept_code="friction-formula-selection",
                pattern_kind=CorrectionPatternKind.FORMULA,
                support_level=EvidenceSupportLevel.SINGLE_OBSERVATION,
                source_revision_id="s",
                curriculum_version_code="v1",
            ),
        ),
        rejected_ids=(),
        issue_codes=(),
    )
    decision, _ = decide_adaptation(
        bundle,
        target_concept_code="friction-formula-selection",
        prior_cycle_count=0,
        practice_completed=True,
        pre_practice_rank=4,
    )
    assert decision is AdaptationDecision.REGRESS


def test_demo_has_three_stages_and_newton_target() -> None:
    plan = AdaptiveRemediationDiagnosticService().run_authoritative_synthetic_demo()
    assert len(plan.stages) >= 3
    assert any(t.concept_code == "newton-laws" for t in plan.targets)


def test_spacing_nonnegative_cycle() -> None:
    assert propose_spacing(date(2026, 1, 1), 0) == date(2026, 1, 2)
    assert propose_spacing(date(2026, 1, 1), -1) is None
