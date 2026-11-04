from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.registry import build_default_registry
from app.models.education_intelligence import ValidationAuditRun
from app.orchestration.contracts import ResolvedScope

_ACCEPTED_DAY6_STATUSES = {"pass", "accepted", "ok", "success"}


def current_day6_provenance(ctx: ValidationContext) -> dict[str, Any]:
    registry = build_default_registry()
    validator_versions = {
        validator_id: registry.get(validator_id).validator_version  # type: ignore[union-attr]
        for validator_id in registry.all_ids()
        if registry.get(validator_id) is not None
    }
    return {
        "taxonomy_version": ctx.taxonomy.version,
        "policy_version": ctx.policy.version,
        "quality_rule_pack_version": (
            ctx.quality_rule_pack.version if ctx.quality_rule_pack else None
        ),
        "safety_rules_version": (ctx.safety_rule_pack.version if ctx.safety_rule_pack else None),
        "validator_versions": validator_versions,
    }


def day6_run_provenance_current(
    record: ValidationAuditRun,
    *,
    taxonomy_version: str,
    policy_version: str,
    quality_rule_pack_version: str | None,
    safety_rules_version: str | None,
    validator_versions: dict[str, str],
) -> bool:
    if str(record.taxonomy_version or "") != str(taxonomy_version):
        return False
    if str(record.policy_version or "") != str(policy_version):
        return False
    meta = record.metadata_json or {}
    stored_quality = meta.get("quality_rule_pack_version")
    if quality_rule_pack_version is not None:
        if str(stored_quality or "") != str(quality_rule_pack_version):
            return False
    stored_safety = meta.get("safety_rules_version")
    if safety_rules_version is not None:
        if str(stored_safety or "") != str(safety_rules_version):
            return False
    stored_validators = meta.get("validator_versions") or {}
    if not isinstance(stored_validators, dict):
        return False
    for validator_id, version in validator_versions.items():
        if str(stored_validators.get(validator_id) or "") != str(version):
            return False
    return True


def find_accepted_day6_audit_run(
    session: Session,
    *,
    item_id: str,
    input_hash: str,
    scope: ResolvedScope,
    taxonomy_version: str,
    policy_version: str,
    quality_rule_pack_version: str | None = None,
    safety_rules_version: str | None = None,
    validator_versions: dict[str, str] | None = None,
) -> ValidationAuditRun | None:
    """Return a persisted non-blocking Day6 run matching canonical input and active versions."""
    if not input_hash:
        return None
    validators = validator_versions or {}
    records = session.scalars(
        select(ValidationAuditRun)
        .where(
            ValidationAuditRun.input_hash == input_hash,
            ValidationAuditRun.blocking_failure.is_(False),
            ValidationAuditRun.taxonomy_version == taxonomy_version,
            ValidationAuditRun.policy_version == policy_version,
        )
        .order_by(ValidationAuditRun.created_at.desc())
    ).all()
    for record in records:
        aggregate = str(record.aggregate_status or "").lower()
        if aggregate not in _ACCEPTED_DAY6_STATUSES:
            continue
        if not day6_run_provenance_current(
            record,
            taxonomy_version=taxonomy_version,
            policy_version=policy_version,
            quality_rule_pack_version=quality_rule_pack_version,
            safety_rules_version=safety_rules_version,
            validator_versions=validators,
        ):
            continue
        validated_items = (record.metadata_json or {}).get("validated_items") or []
        item_entry = next(
            (entry for entry in validated_items if str(entry.get("item_id")) == item_id),
            None,
        )
        if item_entry is None:
            continue
        if str(item_entry.get("input_hash") or "") != str(input_hash):
            continue
        run_scope = (record.metadata_json or {}).get("scope") or {}
        if scope.organization_id and str(run_scope.get("organization_id") or "") != str(
            scope.organization_id
        ):
            continue
        if scope.institution_id and str(run_scope.get("institution_id") or "") != str(
            scope.institution_id
        ):
            continue
        if scope.curriculum_version_id and str(
            run_scope.get("curriculum_version_id") or ""
        ) != str(scope.curriculum_version_id):
            continue
        for field, expected in (
            ("grade_year_code", scope.grade_year_code),
            ("medium_code", scope.medium_code),
            ("subject_code", scope.subject_code),
        ):
            if expected:
                persisted = item_entry.get(field)
                if not persisted or str(persisted) != str(expected):
                    break
        else:
            return record
    return None


def day6_summary_from_audit_run(
    record: ValidationAuditRun,
    *,
    item_id: str,
) -> tuple[str, str, list[str], list[str]]:
    validated_items = (record.metadata_json or {}).get("validated_items") or []
    item_entry = next(
        (entry for entry in validated_items if str(entry.get("item_id")) == item_id),
        None,
    )
    if item_entry is None or not isinstance(item_entry, dict):
        item_entry = {}
    learning_outcome_ids = list(item_entry.get("learning_outcome_ids") or [])
    competency_codes = list(item_entry.get("competency_codes") or [])
    return str(record.id), str(record.input_hash), learning_outcome_ids, competency_codes


def day6_run_versions_current(
    record: ValidationAuditRun,
    *,
    taxonomy_version: str,
    policy_version: str,
    quality_rule_pack_version: str | None = None,
    safety_rules_version: str | None = None,
    validator_versions: dict[str, str] | None = None,
) -> bool:
    return day6_run_provenance_current(
        record,
        taxonomy_version=taxonomy_version,
        policy_version=policy_version,
        quality_rule_pack_version=quality_rule_pack_version,
        safety_rules_version=safety_rules_version,
        validator_versions=validator_versions or {},
    )
