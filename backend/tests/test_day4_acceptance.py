from __future__ import annotations

from copy import deepcopy

import pytest

from app.curriculum_intelligence.acceptance import evaluate_day4_acceptance


def _complete_report() -> dict:
    baseline = {
        "syllabus": {"verified": True},
        "path": {"node_ids": list(range(7))},
        "assessment_checks": {"verified": True},
        "assessment_status": "verified",
        "assessment_pattern": {"status": "verified"},
        "assessment_evidence_id": "synthetic",
    }
    return {
        "minimum_path_verified": True,
        "path": {"node_ids": list(range(7))},
        "framework_structure": {
            "nodes": [
                {"level": level} for level in ["stage", "curricular_area", "goal", "competency"]
            ],
            "learning_outcome_links": ["synthetic"],
        },
        "catalogue_inventory": {
            "extraction_verified": True,
            "index_subject_count": 3,
            "subjects": [
                {
                    "grade_scope": "explicit_single",
                    "review_required": False,
                    "grade_candidates": ["IX"],
                },
                {
                    "grade_scope": "explicit_single",
                    "review_required": False,
                    "grade_candidates": ["X"],
                },
                {
                    "grade_scope": "shared",
                    "review_required": True,
                    "grade_candidates": ["XI", "XII"],
                },
            ],
            "by_grade": {grade: ["synthetic"] for grade in ["IX", "X", "XI", "XII"]},
            "materialized_subject_node_ids": ["node-ix", "node-x"],
            "coverage_denominator": {
                "expected_index_entries": 3,
                "materialized_explicit_grade_entries": 2,
                "not_materialized_entries": 1,
                "unresolved_shared_grade_scope": 1,
                "detailed_syllabus_paths": 3,
            },
        },
        "initial_baselines": [
            dict(deepcopy(baseline), key=key) for key in ["maths-x", "physics-xii"]
        ],
        "assessment_catalogues": {
            key: {"extraction_verified": True, "subject_count": 1}
            for key in ["cbse-class-x-sqp-2026-27", "cbse-class-xii-sqp-2026-27"]
        },
    }


def test_complete_scope_gate_keeps_nonblocking_source_reviews_explicit() -> None:
    report = _complete_report()
    report["initial_baselines"][1]["source_warning"] = "Source header requires review"
    gate = evaluate_day4_acceptance(report)
    assert gate["passed"]
    assert gate["source_reviews"] == ["Source header requires review"]


@pytest.mark.parametrize(
    "missing",
    [
        "minimum_path_verified",
        "framework_structure",
        "catalogue_inventory",
        "initial_baselines",
        "assessment_catalogues",
    ],
)
def test_any_missing_major_component_fails_acceptance(missing: str) -> None:
    report = _complete_report()
    report.pop(missing)
    gate = evaluate_day4_acceptance(report)
    assert not gate["passed"]
    assert gate["incomplete_components"]


def test_missing_senior_grade_catalogue_scope_is_not_hidden() -> None:
    report = _complete_report()
    report["catalogue_inventory"]["by_grade"].pop("XII")
    assert not evaluate_day4_acceptance(report)["passed"]


@pytest.mark.parametrize(
    "defect",
    [
        "zero_materialized",
        "partial_materialized",
        "duplicate_ids",
        "wrong_expected",
        "wrong_materialized",
        "wrong_missing",
        "wrong_shared",
        "wrong_paths",
        "no_eligible",
        "empty_grade",
    ],
)
def test_catalogue_materialization_and_denominators_fail_closed(defect: str) -> None:
    report = _complete_report()
    catalogue = report["catalogue_inventory"]
    if defect == "zero_materialized":
        catalogue["materialized_subject_node_ids"] = []
    elif defect == "partial_materialized":
        catalogue["materialized_subject_node_ids"] = ["node-ix"]
    elif defect == "duplicate_ids":
        catalogue["materialized_subject_node_ids"] = ["same", "same"]
    elif defect == "no_eligible":
        for subject in catalogue["subjects"]:
            subject["review_required"] = True
    elif defect == "empty_grade":
        catalogue["by_grade"]["IX"] = []
    else:
        field = {
            "wrong_expected": "expected_index_entries",
            "wrong_materialized": "materialized_explicit_grade_entries",
            "wrong_missing": "not_materialized_entries",
            "wrong_shared": "unresolved_shared_grade_scope",
            "wrong_paths": "detailed_syllabus_paths",
        }[defect]
        catalogue["coverage_denominator"][field] += 1
    assert not evaluate_day4_acceptance(report)["passed"]
