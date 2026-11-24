from app.ca_imat_eapcet.authority import resolve_imat_authority
from app.ca_imat_eapcet.enums import Day14ProfileKind, PlanVerdict
from app.ca_imat_eapcet.governance import build_day14_governance_record
from app.ca_imat_eapcet.scope_ledger import load_repo_scope_counts
from app.ca_imat_eapcet.source_registry import ca_icai_evidence_ready


def test_d14_01_governance_preserves_deferrals() -> None:
    record = build_day14_governance_record()
    assert record["day11_state"] == "ON_HOLD"
    assert record["day14_founder_approval"] is False
    assert record["day15_state"] == "LOCKED"
    assert record["postgresql_migration_0021"] == "BLOCKER_DEFERRED_NOT_PASSED"
    assert record["core_35_official_intake_live"] is False


def test_d14_scope_map_has_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] >= 1


def test_imat_future_fail_closed() -> None:
    decision = resolve_imat_authority(
        profile_kind=Day14ProfileKind.IMAT_FUTURE_YEAR,
        academic_year="2030",
    )
    assert decision.verdict == PlanVerdict.OFFICIAL_NOT_VERIFIED


def test_ca_not_ready_without_curator() -> None:
    assert ca_icai_evidence_ready() is False