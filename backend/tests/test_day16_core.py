from datetime import date

from app.adaptive_remediation.contracts import (
    AdaptiveRemediationRequest,
    CurriculumScopeRef,
    EvidenceObservation,
)
from app.adaptive_remediation.enums import (
    CorrectionPatternKind,
    EvidenceSupportLevel,
    RemediationVerdict,
)
from app.adaptive_remediation.integration_contracts import build_integration_bridge_status
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService


def _base_request(**overrides: object) -> AdaptiveRemediationRequest:
    base = AdaptiveRemediationRequest(
        request_id="d16-test",
        curriculum_scope=CurriculumScopeRef(
            curriculum_pack_code="d16-synth-physics",
            curriculum_version_code="d16-synth-physics-v1",
            subject_code="physics",
        ),
        target_concept_code="friction-formula-selection",
        observations=(),
        requested_question_count=10,
        as_of_date=date(2026, 11, 24),
    )
    return base.model_copy(update=overrides)


def test_production_gate_always_not_ready() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.run_authoritative_synthetic_demo()
    assert plan.production_gate.verdict is RemediationVerdict.NOT_READY
    assert plan.production_gate.actionable is False
    assert plan.production_gate.delivered_question_count == 0
    assert plan.production_gate.validated_question_count == 0


def test_integration_bridge_contract_only() -> None:
    bridge = build_integration_bridge_status()
    assert bridge.live_calls_permitted is False
    assert bridge.simulated_academic_pass is False


def test_session_injection_blocked() -> None:
    service = AdaptiveRemediationDiagnosticService()

    class FakeSession:
        pass

    plan = service.plan(_base_request(), session=FakeSession())  # type: ignore[arg-type]
    assert plan.production_gate.verdict is RemediationVerdict.BLOCKED


def test_trust_bypass_blocked() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.plan(_base_request(), enable_production=True)  # type: ignore[call-arg]
    assert plan.production_gate.verdict is RemediationVerdict.BLOCKED


def test_cold_start_review_required() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.plan(_base_request())
    assert plan.verdict is RemediationVerdict.REVIEW_REQUIRED


def test_with_evidence_diagnostic_plan() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.plan(
        _base_request(
            observations=(
                EvidenceObservation(
                    observation_id="obs-1",
                    concept_code="friction-formula-selection",
                    pattern_kind=CorrectionPatternKind.FORMULA,
                    support_level=EvidenceSupportLevel.RECURRENT,
                    curriculum_version_code="d16-synth-physics-v1",
                ),
            ),
        )
    )
    assert plan.verdict is RemediationVerdict.DIAGNOSTIC_PLAN
    assert plan.planned_count == 10
