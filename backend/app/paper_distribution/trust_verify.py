from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.education_intelligence.policy_registry import V1_POLICY_VERSION
from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import PaperDistributionRequest
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    paper_targets_authorized,
)
from app.paper_distribution.trusted_validation import (
    SYNTHETIC_PAPER_TRUST_TOKEN,
    PaperDay6TrustContext,
)

_PAPER_AUDIT_KIND = "paper_distribution"
_DAY6_VALIDATION_KIND = "day6_validation"
_DAY6_PASS_STATUSES = {"pass", "accepted", "ok"}


def _validated_items_index(record: ValidationAuditRun) -> dict[str, dict[str, Any]]:
    meta = record.metadata_json or {}
    items = meta.get("validated_items") or []
    index: dict[str, dict[str, Any]] = {}
    for entry in items:
        if isinstance(entry, dict) and entry.get("item_id"):
            index[str(entry["item_id"])] = entry
    return index


def verify_paper_day6_trust(
    session: Session | None,
    request: PaperDistributionRequest,
    trust: PaperDay6TrustContext | None,
    *,
    execution_mode: TrustExecutionMode,
    execution_context: PaperExecutionContext | None = None,
) -> tuple[list[PaperDistributionIssueCode], list[str]]:
    issues: list[PaperDistributionIssueCode] = []
    paths: list[str] = []

    if trust is None:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust")
        return issues, paths

    if trust.trust_source == "synthetic_fixture_harness":
        if execution_mode != TrustExecutionMode.SYNTHETIC_FIXTURE:
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append("day6_trust.synthetic_forbidden")
        elif trust.harness_token != SYNTHETIC_PAPER_TRUST_TOKEN:
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append("day6_trust.harness_token")
        return issues, paths

    if session is None or not trust.validation_run_id:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.validation_run")
        return issues, paths

    record = session.get(ValidationAuditRun, trust.validation_run_id)
    if record is None:
        record = session.scalar(
            select(ValidationAuditRun).where(
                ValidationAuditRun.run_id == trust.validation_run_id
            )
        )
    if record is None:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.validation_run_missing")
        return issues, paths

    meta_kind = str((record.metadata_json or {}).get("kind") or "")
    if meta_kind == _PAPER_AUDIT_KIND:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.paper_audit_not_day6")
        return issues, paths
    if meta_kind and meta_kind != _DAY6_VALIDATION_KIND:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.audit_kind")
        return issues, paths

    if str(record.aggregate_status).lower() not in _DAY6_PASS_STATUSES:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.validation_run_status")

    trusted_institution = (
        execution_context.institution_id if execution_context else None
    ) or (request.metadata_json or {}).get("institution_id")
    scoped_institution = bool(
        (request.metadata_json or {}).get("institution_id")
        or (execution_context and execution_context.institution_id)
    )
    if (
        execution_mode == TrustExecutionMode.PRODUCTION
        and scoped_institution
        and not trusted_institution
    ):
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.institution_required")

    metadata_institution = (request.metadata_json or {}).get("institution_id")
    if (
        execution_context
        and execution_context.institution_id
        and metadata_institution
        and metadata_institution != execution_context.institution_id
    ):
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.metadata_institution_spoof")

    if (
        trusted_institution
        and record.institution_id
        and trusted_institution != record.institution_id
    ):
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.institution_mismatch")

    validated_index = _validated_items_index(record)
    if not validated_index:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.item_coverage")
        return issues, paths

    for index, item in enumerate(request.items):
        base_path = f"items[{index}]"
        validated = validated_index.get(item.item_id)
        if validated is None:
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/item_id")
            continue

        expected_hash = validated.get("input_hash")
        item_hash = (item.metadata_json or {}).get("day6_input_hash")
        if expected_hash and item_hash and str(item_hash) != str(expected_hash):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/metadata_json.day6_input_hash")

        declared_cognitive = validated.get("declared_cognitive_level")
        if (
            item.cognitive_level
            and declared_cognitive
            and str(item.cognitive_level).casefold() != str(declared_cognitive).casefold()
        ):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/cognitive_level")

        validated_comps = set(validated.get("competency_codes") or [])
        if item.competency_codes and validated_comps:
            if not set(item.competency_codes).issubset(validated_comps):
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/competency_codes")

        validated_institution = validated.get("institution_id")
        if (
            trusted_institution
            and validated_institution
            and trusted_institution != validated_institution
        ):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/institution")

    return issues, paths


def verify_target_policy(
    session: Session | None,
    request: PaperDistributionRequest,
    *,
    execution_mode: TrustExecutionMode,
) -> tuple[list[PaperDistributionIssueCode], list[str]]:
    issues: list[PaperDistributionIssueCode] = []
    paths: list[str] = []
    if not request.cognitive_targets and not request.competency_targets:
        return issues, paths

    if execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE:
        return issues, paths

    version = request.target_policy_version or PAPER_TARGET_POLICY_VERSION
    if version == V1_POLICY_VERSION:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        paths.append("target_policy_version")
        return issues, paths

    if session is None:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        paths.append("target_policy_version")
        return issues, paths

    ok, field_path = paper_targets_authorized(session, request, version=version)
    if not ok:
        if field_path == "target_policy_version":
            issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        else:
            issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
        paths.append(field_path or "target_policy_version")

    return issues, paths
