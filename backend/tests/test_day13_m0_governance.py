from app.cuet_clat.authority import resolve_cuet_authority
from app.cuet_clat.enums import CuetClatProfileKind, PlanVerdict
from app.cuet_clat.governance import build_day13_governance_record
from app.cuet_clat.scope_ledger import load_repo_scope_counts
from app.cuet_clat.source_registry import cuet_reference_evidence_ready


def test_d13_01_governance_records_day11_hold() -> None:
    record = build_day13_governance_record()
    assert record["day11_state"] == "ON_HOLD"
    assert record["day13_founder_approval"] is False
    assert record["day14_state"] == "LOCKED"
    assert record["core_35_official_intake_live"] is False
    assert "synthetic_fixture" in record["trust_modes"]


def test_d13_scope_map_has_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] >= 1


def test_cuet_2027_fail_closed() -> None:
    decision = resolve_cuet_authority(
        profile_kind=CuetClatProfileKind.CUET_CANDIDATE_2027,
        academic_year="2027",
    )
    assert decision.verdict == PlanVerdict.OFFICIAL_NOT_VERIFIED
    assert not decision.allow_official_cuet_replica


def test_cuet_reference_not_ready_without_curator() -> None:
    assert cuet_reference_evidence_ready() is False