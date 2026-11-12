from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE, PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.contracts import AdvancedPaperPlanRequest
from app.jee_advanced.enums import (
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.planner import JeeAdvancedPaperPlanner


def test_d12_22_single_paper_full_simulation_fails() -> None:
    planner = JeeAdvancedPaperPlanner()
    result = planner.plan(
        AdvancedPaperPlanRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
            paper_codes=[PAPER_1_CODE],
            simulate_full_pair=True,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.FAIL
    assert result.issue_codes


def test_synthetic_full_pair_assembles_distinct_items() -> None:
    planner = JeeAdvancedPaperPlanner()
    result = planner.plan(
        AdvancedPaperPlanRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
            simulate_full_pair=True,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.PASS
    assert not result.issue_codes
    assert set(result.paper_item_ids) == {PAPER_1_CODE, PAPER_2_CODE}
    all_ids = [qid for ids in result.paper_item_ids.values() for qid in ids]
    assert len(all_ids) == len(set(all_ids))
    assert result.metadata_json.get("demonstration_only") is True


def test_invalid_paper_code_fails_not_pass() -> None:
    planner = JeeAdvancedPaperPlanner()
    result = planner.plan(
        AdvancedPaperPlanRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
            paper_codes=[PAPER_1_CODE, "invalid-paper"],
            simulate_full_pair=False,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.FAIL
    assert result.issue_codes
