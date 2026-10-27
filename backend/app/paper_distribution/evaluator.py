from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

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
    PaperItemInput,
)
from app.paper_distribution.enums import (
    DistributionDimensionStatus,
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)


def _default_marks(item: PaperItemInput) -> float:
    if item.marks is None:
        return 1.0
    return float(item.marks)


def _reconcile_exact_counts(total: int, targets: list[DistributionTarget]) -> dict[str, int]:
    if total <= 0:
        return {}
    exact = [t for t in targets if t.exact_percent is not None]
    if not exact:
        return {}
    raw = {t.key: (t.exact_percent or 0.0) * total / 100.0 for t in exact}
    floors = {k: int(v) for k, v in raw.items()}
    remainder = total - sum(floors.values())
    fractional = sorted(raw.items(), key=lambda kv: (kv[1] - floors[kv[0]], kv[0]), reverse=True)
    result = dict(floors)
    index = 0
    while remainder > 0 and fractional:
        key = fractional[index % len(fractional)][0]
        result[key] = result.get(key, 0) + 1
        remainder -= 1
        index += 1
    return result


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
            audit_ref=str(uuid4()),
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

        marks = _default_marks(item)
        if item.marks is not None and item.marks < 0:
            issues.append(PaperDistributionIssueCode.NEGATIVE_MARKS)
            field_paths.append(f"{base_path}/marks")
        if item.marks is not None and item.marks == 0:
            issues.append(PaperDistributionIssueCode.ZERO_MARKS)
            field_paths.append(f"{base_path}/marks")
        if marks <= 0:
            continue
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
                else:
                    cognitive_counts[resolved] += 1.0
                    cognitive_marks[resolved] += marks

        if request.multi_label_policy == MultiLabelPolicy.FRACTIONAL_SPLIT:
            comp_codes = list(item.competency_codes)
            if not comp_codes:
                issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                field_paths.append(f"{base_path}/competency_codes")
            else:
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
            else:
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
        key: round(100.0 * competency_marks.get(key, 0.0) / mark_den, 2) for key in competency_keys
    }

    cognitive_status = DistributionDimensionStatus.PASS
    competency_status = DistributionDimensionStatus.PASS
    variance: dict[str, float] = {}

    expected_counts = _reconcile_exact_counts(item_count, request.cognitive_targets)
    for target in request.cognitive_targets:
        observed = cognitive_percent.get(target.key, 0.0)
        if target.exact_percent is not None:
            variance[target.key] = round(observed - target.exact_percent, 2)
            expected = expected_counts.get(target.key)
            if expected is not None and cognitive_counts.get(target.key, 0) != expected:
                issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
                cognitive_status = DistributionDimensionStatus.FAIL
        if target.min_percent is not None and observed < target.min_percent:
            issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
            cognitive_status = DistributionDimensionStatus.FAIL
        if target.max_percent is not None and observed > target.max_percent:
            issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
            cognitive_status = DistributionDimensionStatus.FAIL

    if request.include_mark_weighted and request.cognitive_targets:
        for target in request.cognitive_targets:
            if target.exact_percent is None:
                continue
            observed_mark = cognitive_mark_percent.get(target.key, 0.0)
            if abs(observed_mark - target.exact_percent) > 0.01:
                count_obs = cognitive_percent.get(target.key, 0.0)
                if abs(count_obs - target.exact_percent) <= 0.01:
                    issues.append(PaperDistributionIssueCode.COUNT_MARK_DISAGREEMENT)
                    cognitive_status = DistributionDimensionStatus.REVIEW_REQUIRED

    total_target_percent = sum(
        t.exact_percent or 0.0 for t in request.cognitive_targets if t.exact_percent is not None
    )
    if total_target_percent > 100.0 + 1e-6:
        issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
        cognitive_status = DistributionDimensionStatus.INFEASIBLE

    missing_cognitive = [
        key for key in COGNITIVE_PROGRESSION_ORDER if cognitive_counts.get(key, 0.0) == 0.0
    ]

    verdict = PaperDistributionVerdict.PASS
    if issues:
        if cognitive_status == DistributionDimensionStatus.FAIL or any(
            code
            in {
                PaperDistributionIssueCode.DUPLICATE_ITEM_ID,
                PaperDistributionIssueCode.CREATE_LEVEL_REJECTED,
                PaperDistributionIssueCode.EMPTY_PAPER,
            }
            for code in issues
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
            count_percent=cognitive_percent,
            mark_weighted_percent=cognitive_mark_percent,
            missing_coverage=missing_cognitive,
            status=cognitive_status,
            variance=variance,
        ),
        competency_summary=DimensionSummary(
            dimension="competency",
            counts={k: int(round(competency_counts.get(k, 0))) for k in competency_keys},
            count_percent=competency_percent,
            mark_weighted_percent=competency_mark_percent,
            missing_coverage=[k for k in competency_keys if competency_counts.get(k, 0) == 0],
            status=competency_status,
        ),
        issue_codes=list(dict.fromkeys(issues)),
        field_paths=field_paths,
        audit_ref=str(uuid4()),
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
