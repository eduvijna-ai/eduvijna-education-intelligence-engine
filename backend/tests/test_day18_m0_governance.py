from app.frontend_product.governance import build_day18_governance_record


def test_day18_governance_records_holds() -> None:
    record = build_day18_governance_record()
    assert record["day17_pr61"] == "HELD"
    assert record["day15_pr57"] == "HELD"
    assert record["day11_pr31"] == "HELD"
    assert record["ui_authority"] == "DENY_BY_DEFAULT"
    assert record["day19_unlock"] is False