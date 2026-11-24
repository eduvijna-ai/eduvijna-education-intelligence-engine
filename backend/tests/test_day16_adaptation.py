from datetime import date

from app.adaptive_remediation.adaptation import decide_adaptation, propose_spacing
from app.adaptive_remediation.enums import AdaptationDecision
from app.adaptive_remediation.evidence import NormalizedEvidenceBundle
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService


def test_practice_completion_does_not_auto_improve_without_support() -> None:
    decision, _ = decide_adaptation(
        NormalizedEvidenceBundle(accepted=(), rejected_ids=(), issue_codes=()),
        target_concept_code="friction-formula-selection",
        prior_cycle_count=0,
        practice_completed=True,
    )
    assert decision is AdaptationDecision.INSUFFICIENT_EVIDENCE


def test_demo_has_three_stages() -> None:
    plan = AdaptiveRemediationDiagnosticService().run_authoritative_synthetic_demo()
    assert len(plan.stages) >= 3


def test_spacing_deterministic() -> None:
    d0 = propose_spacing(date(2026, 1, 1), 0)
    d1 = propose_spacing(date(2026, 1, 1), 1)
    assert d0 == date(2026, 1, 2)
    assert d1 == date(2026, 1, 4)
