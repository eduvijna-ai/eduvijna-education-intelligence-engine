from __future__ import annotations

from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import (
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.paper_distribution.fixtures import (
    build_demo_ten_question_paper,
    build_mismatched_target_paper,
)


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


def test_single_partial_cognitive_target_passes() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="cognitive", key="remember", exact_percent=20.0),
            ],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.cognitive_summary.status.value == "pass"


def test_mismatched_target_fails_paper_not_items() -> None:
    base = build_demo_ten_question_paper()
    mismatched = build_mismatched_target_paper(base)
    result = evaluate_paper_distribution(mismatched, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert result.item_count == 10


def test_competency_target_mismatch_fails() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "competency_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_percent=100.0),
            ],
        }
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert result.competency_summary.status.value != "pass"


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
            "items": [item],
            "day6_items_trusted": True,
            "multi_label_policy": MultiLabelPolicy.FRACTIONAL_SPLIT,
            "cognitive_targets": [],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(updated, taxonomy=TaxonomyRegistry())
    assert result.competency_summary.fractional_counts.get("knowledge") == 0.5
    assert result.competency_summary.fractional_counts.get("application") == 0.5
    assert sum(result.competency_summary.fractional_counts.values()) == 1.0
    assert result.competency_summary.counts.get("knowledge") is None
    assert result.competency_summary.fractional_counts.get("knowledge") == 0.5


def test_misplaced_target_dimension_fails() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_percent=100.0),
            ],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert PaperDistributionIssueCode.MALFORMED_TARGET_DIMENSION in result.issue_codes


def test_count_only_without_marks_attributes_items() -> None:
    request = PaperDistributionRequest(
        paper_id="count-only",
        include_mark_weighted=False,
        day6_items_trusted=True,
        items=[
            PaperItemInput(
                item_id="q1",
                marks=None,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                primary_competency_code="knowledge",
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.cognitive_summary.fractional_counts.get("remember") == 1.0
    assert result.competency_summary.fractional_counts.get("knowledge") == 1.0


def test_untrusted_day6_assertion_not_pass() -> None:
    request = PaperDistributionRequest(
        paper_id="untrusted-day6",
        day6_items_trusted=False,
        items=[
            PaperItemInput(
                item_id="q1",
                cognitive_level="remember",
                competency_codes=["knowledge"],
                primary_competency_code="knowledge",
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes
    assert result.verdict != PaperDistributionVerdict.PASS


def test_distinct_fingerprints_for_different_targets() -> None:
    base = build_demo_ten_question_paper()
    other = base.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="cognitive", key="remember", exact_percent=30.0),
            ]
        }
    )
    first = evaluate_paper_distribution(base, taxonomy=TaxonomyRegistry())
    second = evaluate_paper_distribution(other, taxonomy=TaxonomyRegistry())
    assert first.result_fingerprint != second.result_fingerprint


def test_fractional_exact_count_uses_float_shares() -> None:
    request = build_demo_ten_question_paper()
    item = request.items[0].model_copy(
        update={"competency_codes": ["knowledge", "application"], "primary_competency_code": None}
    )
    updated = request.model_copy(
        update={
            "items": [item],
            "day6_items_trusted": True,
            "multi_label_policy": MultiLabelPolicy.FRACTIONAL_SPLIT,
            "cognitive_targets": [],
            "competency_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_count=0),
            ],
        }
    )
    result = evaluate_paper_distribution(updated, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert PaperDistributionIssueCode.TARGET_MISMATCH in result.issue_codes
