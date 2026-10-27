from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.education_intelligence.taxonomy_registry import (
    COGNITIVE_PROGRESSION_ORDER,
    V1_TAXONOMY_VERSION,
    TaxonomyRegistry,
    seed_taxonomy_registry,
)
from app.paper_distribution.contracts import (
    DimensionSummary,
    DistributionTarget,
    PaperDistributionRequest,
    PaperDistributionResult,
)
from app.paper_distribution.enums import (
    DistributionDimensionStatus,
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.prerequisite_intelligence.stable_ids import stable_audit_ref


def _evaluate_dimension_targets(
    dimension: str,
    targets: list[DistributionTarget],
    count_shares: dict[str, float],
    count_percent: dict[str, float],
    mark_percent: dict[str, float],
    item_count: int,
    *,
    include_mark_weighted: bool,
    valid_keys: set[str],
) -> tuple[list[PaperDistributionIssueCode], DistributionDimensionStatus, dict[str, float]]:
    issues: list[PaperDistributionIssueCode] = []
    status = DistributionDimensionStatus.PASS
    variance: dict[str, float] = {}
    seen_keys: set[str] = set()

    scoped = [target for target in targets if target.dimension == dimension]
    if not scoped:
        return issues, status, variance

    for target in scoped:
        if target.key in seen_keys:
            issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
            status = DistributionDimensionStatus.FAIL
        seen_keys.add(target.key)
        if target.key not in valid_keys:
            issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
            status = DistributionDimensionStatus.FAIL
            continue

        observed_count = count_shares.get(target.key, 0.0)
        observed_percent = count_percent.get(target.key, 0.0)

        if target.exact_count is not None:
            if int(round(observed_count)) != target.exact_count:
                issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
                status = DistributionDimensionStatus.FAIL
            variance[target.key] = round(observed_count - float(target.exact_count), 2)

        if target.exact_percent is not None:
            variance[target.key] = round(observed_percent - target.exact_percent, 2)
            if abs(observed_percent - target.exact_percent) > 0.01:
                issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
                status = DistributionDimensionStatus.FAIL
            if include_mark_weighted:
                observed_mark = mark_percent.get(target.key, 0.0)
                if abs(observed_mark - target.exact_percent) > 0.01 and abs(
                    observed_percent - target.exact_percent
                ) <= 0.01:
                    issues.append(PaperDistributionIssueCode.COUNT_MARK_DISAGREEMENT)
                    if status == DistributionDimensionStatus.PASS:
                        status = DistributionDimensionStatus.REVIEW_REQUIRED

        if target.min_percent is not None and observed_percent < target.min_percent:
            issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
            status = DistributionDimensionStatus.FAIL
        if target.max_percent is not None and observed_percent > target.max_percent:
            issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
            status = DistributionDimensionStatus.FAIL

    total_exact = sum(
        target.exact_percent or 0.0 for target in scoped if target.exact_percent is not None
    )
    if total_exact > 100.0 + 1e-6:
        issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
        status = DistributionDimensionStatus.INFEASIBLE

    return issues, status, variance


def evaluate_paper_distribution(
    request: PaperDistributionRequest,
    *,
    taxonomy: TaxonomyRegistry | None = None,
) -> PaperDistributionResult:
    taxonomy = taxonomy or TaxonomyRegistry()
    issues: list[PaperDistributionIssueCode] = []
    field_paths: list[str] = []

    if request.taxonomy_version != V1_TAXONOMY_VERSION:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        field_paths.append("taxonomy_version")

    if not request.items:
        issues.append(PaperDistributionIssueCode.EMPTY_PAPER)
        return PaperDistributionResult(
            paper_id=request.paper_id,
            verdict=PaperDistributionVerdict.FAIL,
            item_count=0,
            distinct_item_ids=[],
            cognitive_summary=DimensionSummary(dimension="cognitive"),
            competency_summary=DimensionSummary(dimension="competency"),
            issue_codes=issues,
            field_paths=field_paths,
            audit_ref=stable_audit_ref("paper", request.paper_id, "empty"),
        )

    seen_ids: set[str] = set()
    distinct_ids: list[str] = []
    cognitive_counts: dict[str, float] = defaultdict(float)
    cognitive_marks: dict[str, float] = defaultdict(float)
    competency_counts: dict[str, float] = defaultdict(float)
    competency_marks: dict[str, float] = defaultdict(float)
    total_marks = 0.0

    for index, item in enumerate(request.items):
        base_path = f"items[{index}]"
        if item.item_id in seen_ids:
            issues.append(PaperDistributionIssueCode.DUPLICATE_ITEM_ID)
            field_paths.append(f"{base_path}/item_id")
            continue
        seen_ids.add(item.item_id)
        distinct_ids.append(item.item_id)

        if not item.day6_validated:
            issues.append(PaperDistributionIssueCode.MISSING_COGNITIVE)
            field_paths.append(f"{base_path}/day6_validated")
            continue

        if item.marks is None:
            if request.include_mark_weighted:
                issues.append(PaperDistributionIssueCode.INVALID_MARKS)
                field_paths.append(f"{base_path}/marks")
            marks = 0.0
        else:
            marks = float(item.marks)

        if item.marks is not None and item.marks < 0:
            issues.append(PaperDistributionIssueCode.NEGATIVE_MARKS)
            field_paths.append(f"{base_path}/marks")
        if item.marks is not None and item.marks == 0:
            issues.append(PaperDistributionIssueCode.ZERO_MARKS)
            field_paths.append(f"{base_path}/marks")
        if marks > 0:
            total_marks += marks

        if not item.cognitive_level:
            issues.append(PaperDistributionIssueCode.MISSING_COGNITIVE)
            field_paths.append(f"{base_path}/cognitive_level")
        else:
            raw = item.cognitive_level.strip().lower()
            if raw == "create":
                issues.append(PaperDistributionIssueCode.CREATE_LEVEL_REJECTED)
                field_paths.append(f"{base_path}/cognitive_level")
            else:
                resolved, _ = taxonomy.resolve_cognitive(item.cognitive_level)
                if resolved is None:
                    issues.append(PaperDistributionIssueCode.INVALID_COGNITIVE)
                    field_paths.append(f"{base_path}/cognitive_level")
                elif marks > 0:
                    cognitive_counts[resolved] += 1.0
                    cognitive_marks[resolved] += marks

        if request.multi_label_policy == MultiLabelPolicy.FRACTIONAL_SPLIT:
            comp_codes = list(item.competency_codes)
            if not comp_codes:
                issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                field_paths.append(f"{base_path}/competency_codes")
            elif marks > 0:
                share = 1.0 / len(comp_codes)
                for code in comp_codes:
                    resolved, _ = taxonomy.resolve_competency(code)
                    if resolved is None:
                        issues.append(PaperDistributionIssueCode.INVALID_COMPETENCY)
                        field_paths.append(f"{base_path}/competency_codes")
                    else:
                        competency_counts[resolved] += share
                        competency_marks[resolved] += marks * share
        else:
            primary = item.primary_competency_code or (
                item.competency_codes[0] if item.competency_codes else None
            )
            if not primary:
                issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                field_paths.append(f"{base_path}/competency_codes")
            elif marks > 0:
                resolved, _ = taxonomy.resolve_competency(primary)
                if resolved is None:
                    issues.append(PaperDistributionIssueCode.INVALID_COMPETENCY)
                    field_paths.append(f"{base_path}/competency_codes")
                else:
                    competency_counts[resolved] += 1.0
                    competency_marks[resolved] += marks

    item_count = len(distinct_ids)
    count_den = float(item_count) if item_count else 1.0
    mark_den = total_marks if total_marks > 0 else 1.0

    cognitive_percent = {
        key: round(100.0 * cognitive_counts.get(key, 0.0) / count_den, 2)
        for key in COGNITIVE_PROGRESSION_ORDER
    }
    cognitive_mark_percent = {
        key: round(100.0 * cognitive_marks.get(key, 0.0) / mark_den, 2)
        for key in COGNITIVE_PROGRESSION_ORDER
    }
    competency_keys = list(taxonomy.competencies.keys())
    competency_percent = {
        key: round(100.0 * competency_counts.get(key, 0.0) / count_den, 2)
        for key in competency_keys
    }
    competency_mark_percent = {
        key: round(100.0 * competency_marks.get(key, 0.0) / mark_den, 2)
        for key in competency_keys
    }

    cognitive_target_issues, cognitive_status, cognitive_variance = _evaluate_dimension_targets(
        "cognitive",
        request.cognitive_targets,
        cognitive_counts,
        cognitive_percent,
        cognitive_mark_percent,
        item_count,
        include_mark_weighted=request.include_mark_weighted,
        valid_keys=set(COGNITIVE_PROGRESSION_ORDER),
    )
    competency_target_issues, competency_status, competency_variance = _evaluate_dimension_targets(
        "competency",
        request.competency_targets,
        competency_counts,
        competency_percent,
        competency_mark_percent,
        item_count,
        include_mark_weighted=request.include_mark_weighted,
        valid_keys=set(competency_keys),
    )
    issues.extend(cognitive_target_issues)
    issues.extend(competency_target_issues)

    missing_cognitive = [
        key for key in COGNITIVE_PROGRESSION_ORDER if cognitive_counts.get(key, 0.0) == 0.0
    ]

    verdict = PaperDistributionVerdict.PASS
    if issues:
        fail_statuses = {
            DistributionDimensionStatus.FAIL,
            DistributionDimensionStatus.INFEASIBLE,
        }
        if (
            cognitive_status in fail_statuses
            or competency_status in fail_statuses
            or any(
                code
                in {
                    PaperDistributionIssueCode.DUPLICATE_ITEM_ID,
                    PaperDistributionIssueCode.CREATE_LEVEL_REJECTED,
                    PaperDistributionIssueCode.EMPTY_PAPER,
                    PaperDistributionIssueCode.TARGET_MISMATCH,
                }
                for code in issues
            )
        ):
            verdict = PaperDistributionVerdict.FAIL
        else:
            verdict = PaperDistributionVerdict.REVIEW_REQUIRED

    return PaperDistributionResult(
        paper_id=request.paper_id,
        verdict=verdict,
        item_count=item_count,
        distinct_item_ids=distinct_ids,
        cognitive_summary=DimensionSummary(
            dimension="cognitive",
            counts={k: int(cognitive_counts.get(k, 0)) for k in COGNITIVE_PROGRESSION_ORDER},
            fractional_counts=dict(cognitive_counts),
            count_percent=cognitive_percent,
            mark_weighted_percent=cognitive_mark_percent,
            missing_coverage=missing_cognitive,
            status=cognitive_status,
            variance=cognitive_variance,
        ),
        competency_summary=DimensionSummary(
            dimension="competency",
            counts={k: int(competency_counts.get(k, 0)) for k in competency_keys},
            fractional_counts=dict(competency_counts),
            count_percent=competency_percent,
            mark_weighted_percent=competency_mark_percent,
            missing_coverage=[k for k in competency_keys if competency_counts.get(k, 0) == 0],
            status=competency_status,
            variance=competency_variance,
        ),
        issue_codes=list(dict.fromkeys(issues)),
        field_paths=field_paths,
        audit_ref=stable_audit_ref(request.paper_id, str(item_count), request.taxonomy_version),
        metadata_json={
            "multi_label_policy": request.multi_label_policy.value,
            "total_marks": total_marks,
        },
    )


def evaluate_paper_distribution_with_session(
    session: Session, request: PaperDistributionRequest
) -> PaperDistributionResult:
    taxonomy = seed_taxonomy_registry(session)
    return evaluate_paper_distribution(request, taxonomy=taxonomy)
