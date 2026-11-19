"""D12-CORE-03: Source-attested scoring preview (complete persisted rubric required)."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.scoring import MultiSelectScoreRule, validate_multi_select_rule
from app.jee_advanced.source_authority import evaluate_revision_trusted
from app.models import ExamBlueprintRule
from app.models.enums import BlueprintRuleType

_MARKING_RULE_TYPES = frozenset({BlueprintRuleType.SCORING.value})


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


def _rule_field_completeness(rule_row: ExamBlueprintRule) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if rule_row.marks_per_question is None:
        issues.append("missing_persisted_full_marks")
    if rule_row.negative_marks is None:
        issues.append("missing_persisted_negative_marks")
    selector = dict(rule_row.selector_json or {})
    if selector.get("partial_marks") is None:
        issues.append("missing_persisted_partial_policy")
    if "allow_proper_subset_partial" not in selector:
        issues.append("missing_partial_answer_policy")
    if not str(selector.get("paper_code") or (rule_row.metadata_json or {}).get("paper_code")):
        issues.append("missing_paper_binding")
    return len(issues) == 0, issues


def _marks_match_persisted_rule(
    rules: dict[str, Any], rule_row: ExamBlueprintRule
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    selector = dict(rule_row.selector_json or {})

    complete, completeness_issues = _rule_field_completeness(rule_row)
    if not complete:
        return False, completeness_issues

    persisted_full = float(rule_row.marks_per_question)  # type: ignore[arg-type]
    persisted_negative = float(rule_row.negative_marks)  # type: ignore[arg-type]
    selector_partial = float(selector["partial_marks"])  # guaranteed present

    def _close(a: float, b: object | None) -> bool:
        if b is None or not isinstance(b, (int, float)):
            return False
        try:
            return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False

    caller_full = rules.get("full_marks") or rules.get("correct_marks")
    if caller_full is None or not isinstance(caller_full, (int, float)):
        issues.append("caller_full_marks_missing")
    elif not _close(persisted_full, caller_full):
        issues.append("caller_full_marks_mismatch")

    caller_neg = rules.get("negative_marks")
    if caller_neg is None or not isinstance(caller_neg, (int, float)):
        issues.append("caller_negative_marks_missing")
    elif not _close(persisted_negative, caller_neg):
        issues.append("caller_negative_marks_mismatch")

    caller_partial = rules.get("partial_marks")
    if caller_partial is None or not isinstance(caller_partial, (int, float)):
        issues.append("caller_partial_marks_missing")
    elif not _close(selector_partial, caller_partial):
        issues.append("caller_partial_marks_mismatch")

    if "allow_proper_subset_partial" in rules:
        caller_partial_policy = bool(rules["allow_proper_subset_partial"])
        stored_policy = bool(selector.get("allow_proper_subset_partial", True))
        if caller_partial_policy != stored_policy:
            issues.append("partial_policy_mismatch")

    return len(issues) == 0, issues


def build_attested_scoring_preview(
    session: Session,
    *,
    rules: dict[str, Any],
    approved_source_revision_id: str,
    blueprint_rule_id: str,
    exam_version_id: str | None = None,
    paper_code: str | None = None,
    section_code: str | None = None,
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

    if not evaluate_revision_trusted(session, approved_source_revision_id):
        base["attestation_issues"] = ["revision_not_trusted"]
        return base

    rule_row = session.get(ExamBlueprintRule, blueprint_rule_id)
    if rule_row is None:
        base["attestation_issues"] = ["blueprint_rule_missing"]
        return base

    if rule_row.rule_type not in _MARKING_RULE_TYPES:
        base["attestation_issues"] = ["blueprint_rule_not_marking_type"]
        return base

    if exam_version_id is None:
        base["attestation_issues"] = ["exam_version_id_required"]
        return base
    if rule_row.exam_version_id != exam_version_id:
        base["attestation_issues"] = ["blueprint_exam_version_mismatch"]
        return base

    rule_meta = dict(rule_row.metadata_json or {})
    selector_json = dict(rule_row.selector_json or {})
    rule_paper = str(rule_meta.get("paper_code") or selector_json.get("paper_code") or "")
    rule_section = str(rule_meta.get("section_code") or selector_json.get("section_code") or "")
    if paper_code is not None and rule_paper and paper_code != rule_paper:
        base["attestation_issues"] = ["paper_section_mismatch"]
        return base
    if section_code is not None and rule_section and section_code != rule_section:
        base["attestation_issues"] = ["paper_section_mismatch"]
        return base

    pinned_meta = selector_json.get("source_pinned_revision_id")
    if not pinned_meta:
        base["attestation_issues"] = ["blueprint_source_pin_missing"]
        return base
    if str(pinned_meta) != approved_source_revision_id:
        base["attestation_issues"] = ["blueprint_source_revision_mismatch"]
        return base

    rule_valid, rule_issues = _rules_marking_valid(rules)
    if not rule_valid:
        base["attestation_issues"] = rule_issues
        return base

    marks_ok, marks_issues = _marks_match_persisted_rule(rules, rule_row)
    if not marks_ok:
        base["attestation_issues"] = marks_issues
        return base

    return {
        **base,
        "source_pinned": True,
        "demonstration_only": False,
        "attestation_issues": [],
        "exam_version_id": rule_row.exam_version_id,
        "blueprint_rule_type": rule_row.rule_type,
    }