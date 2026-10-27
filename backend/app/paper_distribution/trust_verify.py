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

    if execution_mode == TrustExecutionMode.PRODUCTION and execution_context is None:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.execution_context")
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

    if record.blocking_failure:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.blocking_failure")

    if str(record.aggregate_status).lower() not in _DAY6_PASS_STATUSES:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.validation_run_status")

    trusted_institution = (
        execution_context.institution_id if execution_context else None
    )
    if execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE and not trusted_institution:
        trusted_institution = (request.metadata_json or {}).get("institution_id")

    metadata_institution = (request.metadata_json or {}).get("institution_id")
    if (
        execution_mode == TrustExecutionMode.PRODUCTION
        and metadata_institution
        and execution_context
        and metadata_institution != execution_context.institution_id
    ):
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.metadata_institution_spoof")

    if execution_mode == TrustExecutionMode.PRODUCTION and trusted_institution:
        if record.institution_id and trusted_institution != record.institution_id:
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append("day6_trust.institution_mismatch")
        elif record.institution_id is None and trusted_institution:
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append("day6_trust.institution_missing_on_run")

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
        if execution_mode == TrustExecutionMode.PRODUCTION:
            if not expected_hash or not item_hash or str(item_hash) != str(expected_hash):
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/metadata_json.day6_input_hash")
        elif expected_hash and item_hash and str(item_hash) != str(expected_hash):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/metadata_json.day6_input_hash")

        declared_cognitive = validated.get("declared_cognitive_level")
        if execution_mode == TrustExecutionMode.PRODUCTION:
            if not declared_cognitive or not item.cognitive_level:
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/cognitive_level")
            elif str(item.cognitive_level).casefold() != str(declared_cognitive).casefold():
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/cognitive_level")
        elif (
            item.cognitive_level
            and declared_cognitive
            and str(item.cognitive_level).casefold() != str(declared_cognitive).casefold()
        ):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append(f"{base_path}/cognitive_level")

        validated_comps = set(validated.get("competency_codes") or [])
        if execution_mode == TrustExecutionMode.PRODUCTION:
            if not validated_comps or not item.competency_codes:
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/competency_codes")
            elif not set(item.competency_codes).issubset(validated_comps):
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/competency_codes")
        elif item.competency_codes and validated_comps:
            if not set(item.competency_codes).issubset(validated_comps):
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/competency_codes")

        if execution_mode == TrustExecutionMode.PRODUCTION:
            scope_fields = (
                ("curriculum_version_id", "curriculum_version_id"),
                ("grade_year_code", "grade_year_code"),
                ("medium_code", "medium_code"),
                ("subject_code", "subject_code"),
            )
            for validated_key, meta_key in scope_fields:
                validated_val = validated.get(validated_key)
                if not validated_val:
                    issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                    paths.append(f"{base_path}/day6.{validated_key}")
                    continue
                paper_val = (item.metadata_json or {}).get(meta_key)
                if not paper_val or str(paper_val) != str(validated_val):
                    issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                    paths.append(f"{base_path}/metadata_json.{meta_key}")

            validated_lo = list(validated.get("learning_outcome_ids") or [])
            if not validated_lo:
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/day6.learning_outcome_ids")
            else:
                paper_lo = (item.metadata_json or {}).get("learning_outcome_ids")
                if not paper_lo or sorted(str(x) for x in paper_lo) != sorted(
                    str(x) for x in validated_lo
                ):
                    issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                    paths.append(f"{base_path}/metadata_json.learning_outcome_ids")
        else:
            validated_curriculum = validated.get("curriculum_version_id")
            paper_curriculum = (item.metadata_json or {}).get("curriculum_version_id")
            if (
                validated_curriculum
                and paper_curriculum
                and validated_curriculum != paper_curriculum
            ):
                issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
                paths.append(f"{base_path}/metadata_json.curriculum_version_id")

        validated_institution = validated.get("institution_id")
        if execution_mode == TrustExecutionMode.PRODUCTION and trusted_institution:
            if validated_institution and trusted_institution != validated_institution:
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
