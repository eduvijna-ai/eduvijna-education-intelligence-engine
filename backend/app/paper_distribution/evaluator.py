from __future__ import annotations

import json
import math
from collections import defaultdict

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.education_intelligence.registry_versions import RegistryVersionNotFound
from app.education_intelligence.taxonomy_registry import (
    COGNITIVE_PROGRESSION_ORDER,
    V1_TAXONOMY_VERSION,
    TaxonomyRegistry,
    seed_taxonomy_registry,
)
from app.paper_distribution.audit import persist_paper_distribution_audit
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
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    load_active_paper_target_policy,
    merge_mandatory_distribution_targets,
)
from app.paper_distribution.trust_verify import verify_paper_day6_trust, verify_target_policy
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.stable_ids import stable_audit_ref


def reconcile_exact_counts(
    item_count: int, targets: list[DistributionTarget]
) -> dict[str, int]:
    """Largest-remainder integer allocation for exact_percent targets summing to 100."""
    if item_count <= 0:
        return {}
    percent_targets = sorted(
        [target for target in targets if target.exact_percent is not None],
        key=lambda target: target.key,
    )
    if not percent_targets:
        return {}
    total_percent = sum(target.exact_percent or 0.0 for target in percent_targets)
    if abs(total_percent - 100.0) > 0.01:
        return {}
    raw_shares = [
        (target.key, (target.exact_percent or 0.0) * item_count / 100.0)
        for target in percent_targets
    ]
    floors = {key: int(math.floor(share)) for key, share in raw_shares}
    assigned = sum(floors.values())
    remainder = item_count - assigned
    if remainder > 0:
        ranked = sorted(
            raw_shares,
            key=lambda entry: (entry[1] - math.floor(entry[1])),
            reverse=True,
        )
        for index in range(remainder):
            key = ranked[index % len(ranked)][0]
            floors[key] = floors.get(key, 0) + 1
    return floors


def _with_mandatory_targets(
    session: Session | None,
    request: PaperDistributionRequest,
    *,
    execution_mode: TrustExecutionMode,
) -> PaperDistributionRequest:
    if execution_mode != TrustExecutionMode.PRODUCTION or session is None:
        return request
    version = request.target_policy_version or PAPER_TARGET_POLICY_VERSION
    try:
        payload = load_active_paper_target_policy(session, version)
    except RegistryVersionNotFound:
        return request
    cognitive, competency = merge_mandatory_distribution_targets(request, payload)
    if (
        cognitive == list(request.cognitive_targets)
        and competency == list(request.competency_targets)
    ):
        return request
    return request.model_copy(
        update={"cognitive_targets": cognitive, "competency_targets": competency}
    )


def _result_fingerprint(request: PaperDistributionRequest) -> str:
    encoded = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return stable_audit_ref("paper-fingerprint", encoded)


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
    fractional_attribution: bool = False,
) -> tuple[list[PaperDistributionIssueCode], DistributionDimensionStatus, dict[str, float]]:
    issues: list[PaperDistributionIssueCode] = []
    status = DistributionDimensionStatus.PASS
    variance: dict[str, float] = {}
    seen_keys: set[str] = set()

    scoped = [target for target in targets if target.dimension == dimension]
    if not scoped:
        return issues, status, variance

    reconciled = (
        reconcile_exact_counts(item_count, scoped) if not fractional_attribution else {}
    )
    percent_targets = [target for target in scoped if target.exact_percent is not None]
    uses_reconciled = (
        bool(reconciled)
        and len(reconciled) == len(percent_targets)
        and not fractional_attribution
    )

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
            expected = float(target.exact_count)
            tolerance = 0.01 if fractional_attribution else 1e-6
            if abs(observed_count - expected) > tolerance:
                issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
                status = DistributionDimensionStatus.FAIL
            variance[target.key] = round(observed_count - expected, 2)

        if target.exact_percent is not None:
            variance[target.key] = round(observed_percent - target.exact_percent, 2)
            if uses_reconciled:
                expected_count = reconciled.get(target.key)
                if expected_count is not None and abs(observed_count - expected_count) > 1e-6:
                    issues.append(PaperDistributionIssueCode.TARGET_MISMATCH)
                    status = DistributionDimensionStatus.FAIL
            elif abs(observed_percent - target.exact_percent) > 0.01:
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

        if (
            target.min_percent is not None
            and target.max_percent is not None
            and target.min_percent > target.max_percent
        ):
            issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
            status = DistributionDimensionStatus.INFEASIBLE

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
    day6_trust: PaperDay6TrustContext | None = None,
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
    data_session: Session | None = None,
    execution_context: PaperExecutionContext | None = None,
) -> PaperDistributionResult:
    taxonomy = taxonomy or TaxonomyRegistry()
    issues: list[PaperDistributionIssueCode] = []
    field_paths: list[str] = []

    if request.taxonomy_version != V1_TAXONOMY_VERSION:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        field_paths.append("taxonomy_version")

    policy_issues, policy_paths = verify_target_policy(
        data_session, request, execution_mode=execution_mode
    )
    issues.extend(policy_issues)
    field_paths.extend(policy_paths)

    request = _with_mandatory_targets(data_session, request, execution_mode=execution_mode)

    trust_issues, trust_paths = verify_paper_day6_trust(
        data_session,
        request,
        day6_trust,
        execution_mode=execution_mode,
        execution_context=execution_context,
    )
    issues.extend(trust_issues)
    field_paths.extend(trust_paths)

    for index, target in enumerate(request.cognitive_targets):
        if target.dimension != "cognitive":
            issues.append(PaperDistributionIssueCode.MALFORMED_TARGET_DIMENSION)
            field_paths.append(f"cognitive_targets[{index}]/dimension")
    for index, target in enumerate(request.competency_targets):
        if target.dimension != "competency":
            issues.append(PaperDistributionIssueCode.MALFORMED_TARGET_DIMENSION)
            field_paths.append(f"competency_targets[{index}]/dimension")

    if request.requested_count is not None and request.requested_count < 0:
        issues.append(PaperDistributionIssueCode.REQUESTED_COUNT_MISMATCH)
        field_paths.append("requested_count")

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
    items_missing_metadata: list[str] = []

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
            items_missing_metadata.append(item.item_id)
            continue

        if trust_issues:
            items_missing_metadata.append(item.item_id)
            continue

        if item.marks is None:
            if request.include_mark_weighted:
                issues.append(PaperDistributionIssueCode.INVALID_MARKS)
                field_paths.append(f"{base_path}/marks")
            marks = 0.0
        else:
            marks = float(item.marks)

        if item.marks is not None and not math.isfinite(item.marks):
            issues.append(PaperDistributionIssueCode.NON_FINITE_MARKS)
            field_paths.append(f"{base_path}/marks")
            marks = 0.0

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
                else:
                    cognitive_counts[resolved] += 1.0
                    if marks > 0:
                        cognitive_marks[resolved] += marks

        if request.multi_label_policy == MultiLabelPolicy.FRACTIONAL_SPLIT:
            comp_codes = list(item.competency_codes)
            if not comp_codes:
                issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                field_paths.append(f"{base_path}/competency_codes")
                items_missing_metadata.append(item.item_id)
            else:
                normalized: list[str] = []
                for code in comp_codes:
                    resolved, _ = taxonomy.resolve_competency(code)
                    if resolved is None:
                        issues.append(PaperDistributionIssueCode.INVALID_COMPETENCY)
                        field_paths.append(f"{base_path}/competency_codes")
                    else:
                        normalized.append(resolved)
                if len(set(normalized)) != len(normalized):
                    issues.append(PaperDistributionIssueCode.DUPLICATE_COMPETENCY_LABEL)
                    field_paths.append(f"{base_path}/competency_codes")
                if normalized:
                    share = 1.0 / len(normalized)
                    for resolved in normalized:
                        competency_counts[resolved] += share
                        if marks > 0:
                            competency_marks[resolved] += marks * share
        else:
            primary = item.primary_competency_code or (
                item.competency_codes[0] if item.competency_codes else None
            )
            if not primary:
                issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                field_paths.append(f"{base_path}/competency_codes")
                items_missing_metadata.append(item.item_id)
            else:
                resolved_codes: list[str] = []
                for code in item.competency_codes:
                    resolved, _ = taxonomy.resolve_competency(code)
                    if resolved is not None:
                        resolved_codes.append(resolved)
                primary_resolved, _ = taxonomy.resolve_competency(primary)
                if primary_resolved is None:
                    issues.append(PaperDistributionIssueCode.INVALID_COMPETENCY)
                    field_paths.append(f"{base_path}/competency_codes")
                elif resolved_codes and primary_resolved not in resolved_codes:
                    issues.append(PaperDistributionIssueCode.PRIMARY_COMPETENCY_MISMATCH)
                    field_paths.append(f"{base_path}/primary_competency_code")
                elif primary_resolved is not None:
                    if not resolved_codes:
                        issues.append(PaperDistributionIssueCode.MISSING_COMPETENCY)
                        field_paths.append(f"{base_path}/competency_codes")
                        items_missing_metadata.append(item.item_id)
                    else:
                        competency_counts[primary_resolved] += 1.0
                        if marks > 0:
                            competency_marks[primary_resolved] += marks

    item_count = len(distinct_ids)
    if request.requested_count is not None and request.requested_count != item_count:
        issues.append(PaperDistributionIssueCode.REQUESTED_COUNT_MISMATCH)
        field_paths.append("requested_count")
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
    competency_fractional = (
        request.multi_label_policy == MultiLabelPolicy.FRACTIONAL_SPLIT
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
        fractional_attribution=competency_fractional,
    )
    issues.extend(cognitive_target_issues)
    issues.extend(competency_target_issues)

    if item_count > 0 and sum(cognitive_counts.values()) < 1e-6:
        issues.append(PaperDistributionIssueCode.ZERO_ITEM_COVERAGE)
        field_paths.append("items")

    missing_cognitive = [
        key for key in COGNITIVE_PROGRESSION_ORDER if cognitive_counts.get(key, 0.0) == 0.0
    ]

    fingerprint = _result_fingerprint(request)

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
                    PaperDistributionIssueCode.MALFORMED_TARGET_DIMENSION,
                    PaperDistributionIssueCode.ZERO_ITEM_COVERAGE,
                    PaperDistributionIssueCode.REQUESTED_COUNT_MISMATCH,
                }
                for code in issues
            )
        ):
            verdict = PaperDistributionVerdict.FAIL
        else:
            verdict = PaperDistributionVerdict.REVIEW_REQUIRED

    if issues and cognitive_status == DistributionDimensionStatus.PASS:
        cognitive_status = DistributionDimensionStatus.REVIEW_REQUIRED
    if issues and competency_status == DistributionDimensionStatus.PASS:
        competency_status = DistributionDimensionStatus.REVIEW_REQUIRED

    return PaperDistributionResult(
        paper_id=request.paper_id,
        verdict=verdict,
        item_count=item_count,
        distinct_item_ids=distinct_ids,
        cognitive_summary=DimensionSummary(
            dimension="cognitive",
            counts={
                k: int(v)
                for k, v in cognitive_counts.items()
                if abs(v - round(v)) < 1e-6
            },
            fractional_counts=dict(cognitive_counts),
            count_percent=cognitive_percent,
            mark_weighted_percent=cognitive_mark_percent,
            missing_coverage=missing_cognitive,
            status=cognitive_status,
            variance=cognitive_variance,
        ),
        competency_summary=DimensionSummary(
            dimension="competency",
            counts={
                k: int(v)
                for k, v in competency_counts.items()
                if abs(v - round(v)) < 1e-6
            },
            fractional_counts=dict(competency_counts),
            count_percent=competency_percent,
            mark_weighted_percent=competency_mark_percent,
            missing_coverage=[k for k in competency_keys if competency_counts.get(k, 0) == 0],
            status=competency_status,
            variance=competency_variance,
        ),
        issue_codes=list(dict.fromkeys(issues)),
        field_paths=field_paths,
        audit_ref=None,
        result_fingerprint=fingerprint,
        metadata_json={
            "multi_label_policy": request.multi_label_policy.value,
            "total_marks": total_marks,
            "items_missing_metadata": items_missing_metadata,
        },
    )


def evaluate_paper_distribution_with_session(
    session: Session,
    request: PaperDistributionRequest,
    *,
    day6_trust: PaperDay6TrustContext | None = None,
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
    execution_context: PaperExecutionContext | None = None,
) -> PaperDistributionResult:
    taxonomy = seed_taxonomy_registry(session)
    if execution_mode == TrustExecutionMode.PRODUCTION:
        ensure_paper_target_policy_configured(session)
    result = evaluate_paper_distribution(
        request,
        taxonomy=taxonomy,
        day6_trust=day6_trust,
        execution_mode=execution_mode,
        data_session=session,
        execution_context=execution_context,
    )
    day6_identity = day6_trust.day6_audit_identity_digest() if day6_trust else None
    audit_ref = persist_paper_distribution_audit(
        session,
        request,
        result,
        execution_context=execution_context,
        execution_mode=execution_mode,
        day6_validation_identity=day6_identity,
    )
    session.flush()
    return result.model_copy(update={"audit_ref": audit_ref})
