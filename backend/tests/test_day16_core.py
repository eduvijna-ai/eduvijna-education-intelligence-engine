import pytest

from app.adaptive_remediation.contracts import ProductionRemediationGate
from app.adaptive_remediation.enums import RemediationVerdict
from app.adaptive_remediation.integration_contracts import build_integration_bridge_status
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService


def test_production_gate_always_not_ready() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.run_authoritative_synthetic_demo()
    assert plan.production_gate.verdict is RemediationVerdict.NOT_READY
    assert plan.production_gate.actionable is False
    assert plan.production_gate.delivered_question_count == 0
    assert plan.production_gate.validated_question_count == 0


def test_production_gate_cannot_be_elevated() -> None:
    with pytest.raises(ValueError):
        ProductionRemediationGate(production_ready=True)


def test_integration_bridge_contract_only() -> None:
    bridge = build_integration_bridge_status()
    assert bridge.live_calls_permitted is False
    assert bridge.simulated_academic_pass is False


def test_runtime_entry_rejects_caller_data() -> None:
    service = AdaptiveRemediationDiagnosticService()

    class Poison:
        @property
        def concept_code(self) -> str:
            return "leaked"

        @property
        def session(self) -> object:
            return object()

    plan = service.attempt_runtime_remediation(Poison(), session=Poison())
    assert plan.planned_count == 0
    assert plan.selected_count == 0
    assert plan.targets == ()
    assert "leaked" not in plan.explanation
    assert plan.metadata_json.get("caller_data_processed") is False


def test_authoritative_demo_diagnostic_plan() -> None:
    service = AdaptiveRemediationDiagnosticService()
    plan = service.run_authoritative_synthetic_demo()
    assert plan.verdict is RemediationVerdict.DIAGNOSTIC_PLAN
    assert plan.planned_count == plan.requested_count == 10
    assert any(t.concept_code == "newton-laws" for t in plan.targets)