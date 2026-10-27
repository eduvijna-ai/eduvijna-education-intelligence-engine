from __future__ import annotations

from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.paper_distribution.enums import MultiLabelPolicy, PaperDistributionIssueCode, PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.paper_distribution.fixtures import build_demo_ten_question_paper, build_mismatched_target_paper


def test_demo_paper_matches_20_20_40_10_10() -> None:
    request = build_demo_ten_question_paper()
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.item_count == 10
    summary = result.cognitive_summary.count_percent
    assert summary["remember"] == 20.0
    assert summary["understand"] == 20.0
    assert summary["apply"] == 40.0
    assert summary["analyze"] == 10.0
    assert summary["evaluate"] == 10.0


def test_mismatched_target_fails_paper_not_items() -> None:
    base = build_demo_ten_question_paper()
    mismatched = build_mismatched_target_paper(base)
    result = evaluate_paper_distribution(mismatched, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert result.item_count == 10


def test_create_level_rejected() -> None:
    request = build_demo_ten_question_paper()
    items = list(request.items)
    items[0] = items[0].model_copy(update={"cognitive_level": "create"})
    result = evaluate_paper_distribution(
        request.model_copy(update={"items": items}),
        taxonomy=TaxonomyRegistry(),
    )
    assert PaperDistributionIssueCode.CREATE_LEVEL_REJECTED in result.issue_codes


def test_fractional_multi_label_conserves_denominator() -> None:
    request = build_demo_ten_question_paper()
    item = request.items[0].model_copy(
        update={
            "competency_codes": ["knowledge", "application"],
            "primary_competency_code": None,
        }
    )
    updated = request.model_copy(
        update={
            "items": [item] + request.items[1:],
            "multi_label_policy": MultiLabelPolicy.FRACTIONAL_SPLIT,
        }
    )
    result = evaluate_paper_distribution(updated, taxonomy=TaxonomyRegistry())
    total_fraction = sum(result.competency_summary.counts.values())
    assert abs(total_fraction - 10.0) < 0.01
