"""Aggregate Day-4 initial-scope evidence, without hiding incomplete components."""

from __future__ import annotations

from typing import Any


def _catalogue_is_complete(catalogue: dict[str, Any], detailed_paths: int) -> bool:
    subjects = catalogue.get("subjects", [])
    eligible = [
        item
        for item in subjects
        if item.get("grade_scope") == "explicit_single"
        and not item.get("review_required")
        and len(item.get("grade_candidates", [])) == 1
        and item["grade_candidates"][0] in {"IX", "X", "XI", "XII"}
    ]
    materialized = catalogue.get("materialized_subject_node_ids", [])
    counts = catalogue.get("coverage_denominator", {})
    shared = sum(item.get("grade_scope") == "shared" for item in subjects)
    return bool(
        catalogue.get("extraction_verified") is True
        and subjects
        and eligible
        and catalogue.get("index_subject_count") == len(subjects)
        and all(catalogue.get("by_grade", {}).get(grade) for grade in ("IX", "X", "XI", "XII"))
        and len(materialized) == len(set(materialized)) == len(eligible)
        and counts.get("expected_index_entries") == len(subjects)
        and counts.get("materialized_explicit_grade_entries") == len(eligible)
        and counts.get("not_materialized_entries") == len(subjects) - len(eligible)
        and counts.get("unresolved_shared_grade_scope") == shared
        and counts.get("detailed_syllabus_paths") == detailed_paths
    )


def evaluate_day4_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    catalogue = report.get("catalogue_inventory") or {}
    structure = report.get("framework_structure") or {}
    baselines = {item.get("key"): item for item in report.get("initial_baselines", [])}
    detailed_paths = int(bool(report.get("minimum_path_verified") and report.get("path"))) + sum(
        bool(item.get("syllabus", {}).get("verified") and item.get("path"))
        for item in baselines.values()
    )
    components = {
        "official_ix_path": bool(report.get("minimum_path_verified") and report.get("path")),
        "framework_structure": (
            {node.get("level") for node in structure.get("nodes", [])}
            == {"stage", "curricular_area", "goal", "competency"}
            and bool(structure.get("learning_outcome_links"))
        ),
        "curriculum_catalogue": _catalogue_is_complete(catalogue, detailed_paths),
    }
    for key in ("maths-x", "physics-xii"):
        baseline = baselines.get(key, {})
        components[key + "_syllabus"] = bool(
            baseline.get("syllabus", {}).get("verified")
            and len(baseline.get("path", {}).get("node_ids", [])) == 7
        )
        components[key + "_assessment"] = bool(
            baseline.get("assessment_checks", {}).get("verified")
            and baseline.get("assessment_status") == "verified"
            and baseline.get("assessment_pattern", {}).get("status") == "verified"
            and baseline.get("assessment_evidence_id")
        )
    for key in ("cbse-class-x-sqp-2026-27", "cbse-class-xii-sqp-2026-27"):
        inventory = report.get("assessment_catalogues", {}).get(key, {})
        components[key + "_inventory"] = bool(
            inventory.get("extraction_verified") and inventory.get("subject_count", 0) > 0
        )
    failed = [key for key, passed in components.items() if not passed]
    return {
        "passed": not failed,
        "components": components,
        "incomplete_components": failed,
        "scope": "Day4 reviewed initial scope; full curriculum-content completeness is not claimed",
        "source_reviews": [
            item["source_warning"] for item in baselines.values() if item.get("source_warning")
        ],
    }
