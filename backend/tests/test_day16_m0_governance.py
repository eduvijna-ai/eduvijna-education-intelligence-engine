from pathlib import Path

from app.adaptive_remediation.dependency_closure import build_dependency_closure_register
from app.adaptive_remediation.governance import build_day16_governance_record
from app.adaptive_remediation.scope_ledger import (
    load_repo_scope_counts,
    validate_scope_map_integrity,
)


def test_day16_governance_freeze() -> None:
    record = build_day16_governance_record()
    assert record["day15_import_forbidden"] is True
    assert record["day14_containment_preserved"]["issuance_disabled"] is True


def test_day16_scope_ledger_36_rows_and_integrity() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "execution" / "D16-SCOPE-MAP.md"
    md = path.read_text(encoding="utf-8")
    ok, issues = validate_scope_map_integrity(md)
    assert ok, issues
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36


def test_day15_blocked_in_dependency_closure() -> None:
    reg = build_dependency_closure_register()
    assert reg["day15_learner_intelligence"] == "ON_HOLD_UNMERGED_PR57_NO_IMPORT"
