"""Aggregate Day-4 initial-scope evidence, without hiding incomplete components."""

from __future__ import annotations

from typing import Any


def evaluate_day4_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    catalogue = report.get("catalogue_inventory") or {}
    structure = report.get("framework_structure") or {}
    baselines = {item.get("key"): item for item in report.get("initial_baselines", [])}
    components = {
        "official_ix_path": bool(report.get("minimum_path_verified") and report.get("path")),
        "framework_structure": (
            {node.get("level") for node in structure.get("nodes", [])}
            == {"stage", "curricular_area", "goal", "competency"}
            and bool(structure.get("learning_outcome_links"))
        ),
        "curriculum_catalogue": (
            catalogue.get("extraction_verified") is True
            and catalogue.get("index_subject_count", 0) > 0
            and {"IX", "X", "XI", "XII"} <= set(catalogue.get("by_grade", {}))
            and bool(catalogue.get("coverage_denominator"))
        ),
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
