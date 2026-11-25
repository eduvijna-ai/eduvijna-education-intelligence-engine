from __future__ import annotations

from app.platform.dependency_closure import build_day17_dependency_closure_register
from app.platform.governance import build_day17_governance_record


def test_day17_governance_preserves_holds() -> None:
    record = build_day17_governance_record()
    assert record["day15_state"] == "ON_HOLD"
    assert record["day16_runtime_remediation"] == "DISABLED"
    assert record["day18_state"] == "LOCKED"
    assert record["founder_approval"] is False


def test_day17_dependency_closure_register() -> None:
    reg = build_day17_dependency_closure_register()
    assert reg["day15_learner_intelligence"]["import_forbidden"] is True
    assert reg["day17_rest_auth_mcp"]["state"] == "ACTIVE"
