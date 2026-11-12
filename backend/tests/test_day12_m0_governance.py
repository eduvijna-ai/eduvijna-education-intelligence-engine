from app.jee_advanced.authority import resolve_profile_authority
from app.jee_advanced.enums import AdvancedPlanVerdict, AdvancedProfileKind
from app.jee_advanced.governance import build_day12_governance_record
from app.jee_advanced.source_registry import reference_evidence_ready


def test_d12_01_governance_records_day11_hold_and_trust_modes() -> None:
    record = build_day12_governance_record()
    assert record["day11_state"] == "ON_HOLD"
    assert record["day12_founder_approval"] is False
    assert record["day13_state"] == "LOCKED"
    assert "synthetic_fixture" in record["trust_modes"]
    assert record["dependency_exception"].startswith("FOUNDER_APPROVED")


def test_d12_05_2027_fail_closed() -> None:
    decision = resolve_profile_authority(
        profile_kind=AdvancedProfileKind.CANDIDATE_2027,
        academic_year="2027",
    )
    assert decision.verdict == AdvancedPlanVerdict.OFFICIAL_PATTERN_NOT_VERIFIED
    assert not decision.allow_official_2027_replica


def test_reference_2026_without_curator_is_not_ready() -> None:
    assert reference_evidence_ready() is False
    decision = resolve_profile_authority(
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    assert decision.verdict == AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED
