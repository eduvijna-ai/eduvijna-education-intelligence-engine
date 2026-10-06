from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.curriculum_intelligence.scoped_acceptance import evaluate_day5_acceptance
from app.repo_paths import ci_workflow_file, curricula_content_dir, repository_root

SCOPE = json.loads((curricula_content_dir() / "day5_scope.json").read_text(encoding="utf-8"))


def test_empty_or_synthetic_report_cannot_pass() -> None:
    for report in (
        {},
        {"synthetic_verification_passed": True},
        {"sources": [{"retrieved_content": True}]},
    ):
        assert not evaluate_day5_acceptance(report, SCOPE)["passed"]


@pytest.mark.parametrize("requirements", [[], [{"key": "same"}, {"key": "same"}]])
def test_missing_or_duplicate_scope_fails(requirements: list[dict[str, str]]) -> None:
    assert not evaluate_day5_acceptance({}, {"required_detailed_slices": requirements})["passed"]


def test_unfrozen_source_scope_never_passes_from_self_claimed_flags() -> None:
    report = {
        "materialized_slices": [
            {
                "key": item["key"],
                "verified_from_persisted_entities": True,
                "exact_bytes_verified": True,
                "applicability_verified": True,
                "source_domain_verified": True,
                "locator_verified": True,
                "synthetic": False,
                "status": "verified",
                "path": {"node_ids": list(range(7))},
            }
            for item in SCOPE["required_detailed_slices"]
        ]
    }
    result = evaluate_day5_acceptance(report, SCOPE)
    assert not result["passed"]
    assert result["verified_detailed_slice_count"] == 0
    corrupt = copy.deepcopy(report)
    corrupt["materialized_slices"].append(corrupt["materialized_slices"][0])
    assert (
        "invalid_required_scope_or_duplicate_evidence"
        in evaluate_day5_acceptance(corrupt, SCOPE)["incomplete_components"]
    )


def test_ci_artifacts_are_metadata_only_and_source_documents_untracked() -> None:
    root = repository_root(start=Path(__file__))
    workflow = ci_workflow_file(start=Path(__file__)).read_text(encoding="utf-8")
    assert "path: backend/evidence/day5-source-report.json" in workflow
    assert "path: backend/data" not in workflow
    assert "path: backend/evidence/" not in workflow.replace(
        "path: backend/evidence/day5-source-report.json", ""
    ).replace("path: backend/evidence/day4-source-report.json", "")
    for path in (root / "content/curricula").iterdir():
        assert path.suffix not in {".pdf", ".docx", ".zip"}


def test_founder_discovery_hypotheses_cannot_satisfy_official_acceptance() -> None:
    scope = copy.deepcopy(SCOPE)
    scope["owner_prose_discovery_hypotheses"] = {
        "status": "founder_provided_unverified_until_exact_official_source_binding",
        "academic_standards_hints": [
            {"code": "AS1", "label": "Conceptual Understanding"},
            {"code": "AS2", "label": "Asking Questions and Making Hypotheses"},
        ],
        "intermediate_group_hints": {
            "general": {
                "MPC": ["Mathematics", "Physics", "Chemistry"],
                "BiPC": ["Botany", "Zoology", "Physics", "Chemistry"],
            }
        },
        "chapter_hints": ["Force", "Friction", "Complex Numbers"],
    }
    result = evaluate_day5_acceptance(
        {
            "owner_prose_discovery_hypotheses": scope[
                "owner_prose_discovery_hypotheses"
            ]
        },
        scope,
    )
    assert not result["passed"]
    assert result["verified_detailed_slice_count"] == 0
