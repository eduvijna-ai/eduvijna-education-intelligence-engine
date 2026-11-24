from app.adaptive_remediation.dependency_closure import build_dependency_closure_register
from app.adaptive_remediation.governance import build_day16_governance_record
from app.adaptive_remediation.scope_ledger import load_repo_scope_counts


def test_day16_governance_freeze() -> None:
    record = build_day16_governance_record()
    assert record["day15_import_forbidden"] is True
    assert record["day15_state"] == "ON_HOLD"
    assert record["day17_state"] == "LOCKED"
    assert record["founder_approval"] is False
    assert record["day14_containment_preserved"]["academic_validation_disabled"] is True
    assert record["day14_containment_preserved"]["issuance_disabled"] is True


def test_day16_scope_ledger_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] == 1
    assert counts["PARTIAL"] == 35


def test_day15_blocked_in_dependency_closure() -> None:
    reg = build_dependency_closure_register()
    assert (
        "0022" in reg["postgresql_migration_0022_day15"]
        or "HELD" in reg["postgresql_migration_0022_day15"]
    )
    assert reg["day15_learner_intelligence"] == "ON_HOLD_UNMERGED_PR57_NO_IMPORT"
