"""D12-CORE-02: Source-attested scoring preview (no caller-forged IDs)."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.scoring import MultiSelectScoreRule, validate_multi_select_rule
from app.jee_advanced.source_authority import evaluate_revision_trusted
from app.models import ExamBlueprintRule
from app.models.enums import BlueprintRuleType

_MARKING_RULE_TYPES = frozenset(
    {
        BlueprintRuleType.SCORING.value,
        BlueprintRuleType.QUESTION_TYPE.value,
    }
)


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


def _marks_match_persisted_rule(
    rules: dict[str, Any], rule_row: ExamBlueprintRule
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    selector = dict(rule_row.selector_json or {})
    persisted_full = rule_row.marks_per_question
    persisted_negative = rule_row.negative_marks
    selector_full = selector.get("full_marks")
    selector_negative = selector.get("negative_marks")
    selector_partial = selector.get("partial_marks")

    def _close(a: float | None, b: object | None) -> bool:
        if a is None or b is None:
            return False
        if not isinstance(b, (int, float)):
            return False
        try:
            return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False

    caller_full = rules.get("full_marks") or rules.get("correct_marks")
    if caller_full is not None:
        ref = persisted_full if persisted_full is not None else selector_full
        if ref is not None and isinstance(caller_full, (int, float)):
            if not _close(float(ref), caller_full):
                issues.append("caller_full_marks_mismatch")
    caller_neg = rules.get("negative_marks")
    if caller_neg is not None:
        ref = persisted_negative if persisted_negative is not None else selector_negative
        if ref is not None and isinstance(caller_neg, (int, float)):
            if not _close(float(ref), caller_neg):
                issues.append("caller_negative_marks_mismatch")
    caller_partial = rules.get("partial_marks")
    if (
        caller_partial is not None
        and selector_partial is not None
        and isinstance(caller_partial, (int, float))
    ):
        if not _close(float(selector_partial), caller_partial):
            issues.append("caller_partial_marks_mismatch")

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

    selector = dict(rule_row.selector_json or {})
    pinned_meta = selector.get("source_pinned_revision_id")
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