from __future__ import annotations

from uuid import uuid4

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    ValidationResult,
    ValidationRunSummary,
)
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.explain import explain_results
from app.education_intelligence.registry import ValidatorRegistry


def _status_rank(status: ValidationStatus) -> int:
    order = {
        ValidationStatus.PASS: 0,
        ValidationStatus.NOT_APPLICABLE: 1,
        ValidationStatus.WARN: 2,
        ValidationStatus.REVIEW_REQUIRED: 3,
        ValidationStatus.FAIL: 4,
    }
    return order.get(status, 99)


def aggregate_status(results: list[ValidationResult]) -> ValidationStatus:
    if any(r.blocking and r.status == ValidationStatus.FAIL for r in results):
        return ValidationStatus.FAIL
    statuses = [r.status for r in results if r.status != ValidationStatus.NOT_APPLICABLE]
    if not statuses:
        return ValidationStatus.NOT_APPLICABLE
    return max(statuses, key=_status_rank)


def bind_provenance(
    results: list[ValidationResult],
    *,
    item: CanonicalAssessmentItem,
    taxonomy_version: str,
    policy_version: str,
) -> list[ValidationResult]:
    input_hash = item.canonical_hash()
    bound: list[ValidationResult] = []
    for result in results:
        bound.append(
            result.model_copy(
                update={
                    "input_hash": input_hash,
                    "taxonomy_version": result.taxonomy_version or taxonomy_version,
                    "policy_version": result.policy_version or policy_version,
                }
            )
        )
    return bound


def run_validation(
    item: CanonicalAssessmentItem,
    ctx: ValidationContext,
    registry: ValidatorRegistry,
    *,
    validator_ids: list[str] | None = None,
    run_id: str | None = None,
) -> ValidationRunSummary:
    selected = validator_ids or registry.all_ids()
    results: list[ValidationResult] = []
    versions: dict[str, str] = {}
    for vid in selected:
        validator = registry.get(vid)
        if validator is None:
            continue
        result = validator.validate(item, ctx)
        results.append(result)
        versions[vid] = validator.validator_version
    results = bind_provenance(
        results,
        item=item,
        taxonomy_version=ctx.taxonomy.version,
        policy_version=ctx.policy.version,
    )
    aggregate = aggregate_status(results)
    blocking_failure = any(r.blocking and r.status == ValidationStatus.FAIL for r in results)
    explanations = explain_results(results)
    return ValidationRunSummary(
        run_id=run_id or str(uuid4()),
        input_hash=item.canonical_hash(),
        aggregate_status=aggregate,
        blocking_failure=blocking_failure,
        results=results,
        taxonomy_version=ctx.taxonomy.version,
        policy_version=ctx.policy.version,
        validator_versions=versions,
        explanations=explanations,
    )
