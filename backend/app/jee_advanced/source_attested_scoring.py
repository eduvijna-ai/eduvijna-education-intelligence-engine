"""D12-CORE-02: Source-attested scoring preview (no caller-forged IDs)."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.scoring import MultiSelectScoreRule, validate_multi_select_rule
from app.jee_advanced.source_authority import evaluate_revision_trusted
from app.models import ExamBlueprintRule, SourceRevision


def _rules_marking_valid(rules: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    rule_type = str(rules.get("rule_type") or rules.get("type") or "").lower()
    if rule_type in {"multi_select", "multiselect"}:
        try:
            ms = MultiSelectScoreRule(
                full_marks=float(rules.get("full_marks", 0)),
                partial_marks=float(rules.get("partial_marks", 0)),
                negative_marks=float(rules.get("negative_marks", 0)),
                allow_proper_subset_partial=bool(
                    rules.get("allow_proper_subset_partial", True)
                ),
            )
        except (TypeError, ValueError):
            issues.append("malformed_multi_select_rule")
            return False, issues
        correct = {str(x) for x in rules.get("correct_options", []) if x}
        if ms.partial_marks > ms.full_marks:
            issues.append("partial_exceeds_full")
        if not validate_multi_select_rule(ms, correct=correct or {"A"}):
            issues.append("invalid_multi_select_marks")
    for key in ("full_marks", "partial_marks", "negative_marks", "correct_marks"):
        if key in rules:
            val = rules[key]
            if not isinstance(val, (int, float)) or not math.isfinite(float(val)):
                issues.append(f"nonfinite_{key}")
            elif float(val) < 0:
                issues.append(f"negative_{key}")
    return len(issues) == 0, issues


def build_attested_scoring_preview(
    session: Session,
    *,
    rules: dict[str, Any],
    approved_source_revision_id: str,
    blueprint_rule_id: str,
    exam_version_id: str | None = None,
) -> dict[str, Any]:
    """Fetch and cross-check revision + blueprint rule; never trust caller-supplied truth."""

    base = {
        "rules": rules,
        "source_pinned": False,
        "demonstration_only": True,
        "approved_source_revision_id": approved_source_revision_id,
        "blueprint_rule_id": blueprint_rule_id,
        "attestation_issues": [],
    }

    revision = session.get(SourceRevision, approved_source_revision_id)
    if revision is None or not evaluate_revision_trusted(session, approved_source_revision_id):
        base["attestation_issues"] = ["revision_not_trusted"]
        return base

    rule_row = session.get(ExamBlueprintRule, blueprint_rule_id)
    if rule_row is None:
        base["attestation_issues"] = ["blueprint_rule_missing"]
        return base

    if exam_version_id and rule_row.exam_version_id != exam_version_id:
        base["attestation_issues"] = ["blueprint_exam_version_mismatch"]
        return base

    rule_valid, rule_issues = _rules_marking_valid(rules)
    if not rule_valid:
        base["attestation_issues"] = rule_issues
        return base

    pinned_meta = (rule_row.selector_json or {}).get("source_pinned_revision_id")
    if pinned_meta and str(pinned_meta) != approved_source_revision_id:
        base["attestation_issues"] = ["blueprint_source_revision_mismatch"]
        return base

    return {
        **base,
        "source_pinned": True,
        "demonstration_only": False,
        "attestation_issues": [],
        "exam_version_id": rule_row.exam_version_id,
        "blueprint_rule_type": rule_row.rule_type,
    }
