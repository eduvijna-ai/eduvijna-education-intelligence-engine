from app.learner_intelligence.governance import build_day15_governance_record
from app.learner_intelligence.scope_ledger import load_repo_scope_counts


def test_d15_01_governance_preserves_deferrals() -> None:
    record = build_day15_governance_record()
    assert record["day11_state"] == "ON_HOLD"
    assert record["day15_founder_approval"] is False
    assert record["day16_state"] == "LOCKED"
    assert record["postgresql_migration_0021"] == "BLOCKER_DEFERRED_NOT_PASSED"
    assert record["production_assessment_eligibility"] is False
    assert record["day14_containment"] == "ACADEMIC_VALIDATION_AND_ISSUANCE_DISABLED"


def test_d15_scope_map_has_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] >= 1