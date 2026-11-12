from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE, PAPER_1_CODE
from app.jee_advanced.contracts import AdvancedPaperPlanRequest
from app.jee_advanced.enums import AdvancedPlanVerdict, AdvancedProfileKind, JeeAdvancedSourceTrustMode
from app.jee_advanced.planner import JeeAdvancedPaperPlanner
from app.jee_advanced.scoring import MultiSelectScoreRule, score_multi_select, score_numerical, NumericalScoreRule


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


def test_d12_24_multi_select_partial_and_penalty() -> None:
    rule = MultiSelectScoreRule(full_marks=4.0, partial_marks=2.0, negative_marks=2.0)
    marks, outcome = score_multi_select(
        selected={"A", "B"},
        correct={"A", "B", "C"},
        rule=rule,
    )
    assert outcome.value == "partial"
    assert marks == 2.0

    marks_bad, outcome_bad = score_multi_select(
        selected={"D"},
        correct={"A", "B"},
        rule=rule,
    )
    assert outcome_bad.value == "incorrect"
    assert marks_bad == -2.0


def test_numerical_tolerance_scoring() -> None:
    rule = NumericalScoreRule(full_marks=3.0, negative_marks=1.0, tolerance=0.05)
    marks, outcome = score_numerical(submitted=2.01, expected=2.0, rule=rule)
    assert outcome.value == "correct"
    assert marks == 3.0
