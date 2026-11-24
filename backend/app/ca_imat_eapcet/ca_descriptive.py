from __future__ import annotations

from app.ca_imat_eapcet.contracts import DescriptiveItemContract
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict
from app.ca_imat_eapcet.scoring import validate_rubric_marks
from app.ca_imat_eapcet.synthetic_fixtures import build_descriptive_sample


def validate_descriptive_item(item: DescriptiveItemContract) -> tuple[PlanVerdict, list[IssueCode]]:
    """D14-11/12: rubric bounds and no automated grading claim."""

    issues: list[IssueCode] = []
    if item.automated_grading_claimed:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
    sub_sum = sum(s.max_marks for s in item.subparts)
    if abs(sub_sum - item.total_marks) > 0.01:
        issues.append(IssueCode.CA_RUBRIC_INVALID)
    criteria = [{"weight": s.max_marks, "id": s.subpart_id} for s in item.subparts]
    ok, rubric_issues = validate_rubric_marks(criteria=criteria, total_marks=item.total_marks)
    issues.extend(rubric_issues)
    if issues:
        return PlanVerdict.REVIEW_REQUIRED, issues
    if not ok:
        return PlanVerdict.FAIL, issues
    return PlanVerdict.PASS, []


def demo_descriptive_contracts() -> list[DescriptiveItemContract]:
    return [
        build_descriptive_sample("paper1_accounting"),
        build_descriptive_sample("paper2_business_laws"),
    ]