from decimal import Decimal

from app.learner_intelligence.diagnostic_pure import pure_missing_item_scoring_diagnostic


def test_pure_missing_item_scoring_4_of_8_no_persistence() -> None:
    result = pure_missing_item_scoring_diagnostic()
    assert result["persisted"] == "false"
    assert result["total_marks"] == str(Decimal("4"))
    assert result["max_marks"] == str(Decimal("8"))