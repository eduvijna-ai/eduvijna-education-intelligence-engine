from __future__ import annotations

import math

from app.ca_imat_eapcet.contracts import DescriptiveItemContract
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict
from app.ca_imat_eapcet.scoring import validate_rubric_marks
from app.ca_imat_eapcet.synthetic_fixtures import (
    build_accounting_descriptive,
    build_business_laws_descriptive,
)


def validate_descriptive_item(item: DescriptiveItemContract) -> tuple[PlanVerdict, list[IssueCode]]:
    """D14-11/12: rubric bounds; no automated grading claim."""

    issues: list[IssueCode] = []
    if item.automated_grading_claimed:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
    seen_ids: set[str] = set()
    for sp in item.subparts:
        if sp.subpart_id in seen_ids:
            issues.append(IssueCode.CA_RUBRIC_INVALID)
        seen_ids.add(sp.subpart_id)
        if not sp.prompt.strip():
            issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        if not math.isfinite(sp.max_marks) or sp.max_marks < 0:
            issues.append(IssueCode.CA_RUBRIC_INVALID)
        lo, hi = sp.partial_credit_bounds
        if not math.isfinite(lo) or not math.isfinite(hi) or lo < 0 or hi < lo or hi > sp.max_marks:
            issues.append(IssueCode.CA_RUBRIC_INVALID)
        if not sp.model_solution_steps:
            issues.append(IssueCode.VALIDATION_NOT_PROVEN)

    sub_sum = sum(s.max_marks for s in item.subparts)
    if abs(sub_sum - item.total_marks) > 0.01:
        issues.append(IssueCode.CA_RUBRIC_INVALID)
    criteria = [{"weight": s.max_marks, "id": s.subpart_id} for s in item.subparts]
    ok, rubric_issues = validate_rubric_marks(criteria=criteria, total_marks=item.total_marks)
    issues.extend(rubric_issues)
    if issues:
        return PlanVerdict.REVIEW_REQUIRED, list(dict.fromkeys(issues))
    if not ok:
        return PlanVerdict.FAIL, issues
    return PlanVerdict.PASS, []


def demo_descriptive_contracts() -> list[DescriptiveItemContract]:
    return [build_accounting_descriptive(), build_business_laws_descriptive()]


def allocate_descriptive_items(
    *,
    paper_code: str,
    requested_count: int,
) -> tuple[PlanVerdict, int, list[DescriptiveItemContract], list[IssueCode]]:
    by_paper = {d.paper_code: d for d in demo_descriptive_contracts()}
    item = by_paper.get(paper_code)
    if item is None:
        return PlanVerdict.FAIL, 0, [], [IssueCode.WRONG_PAPER]
    if requested_count < 1:
        return PlanVerdict.FAIL, 0, [], [IssueCode.INVALID_REQUEST_COUNT]
    if requested_count > 1:
        return PlanVerdict.SHORTAGE, 0, [], [IssueCode.CA_ACCOUNTING_RECONCILE]
    v, issues = validate_descriptive_item(item)
    if v is not PlanVerdict.PASS:
        return v, 0, [], issues
    return PlanVerdict.PASS, 1, [item], []