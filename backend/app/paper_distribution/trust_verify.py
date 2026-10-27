from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.education_intelligence.policy_registry import V1_POLICY_VERSION, load_policy_registry
from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import PaperDistributionRequest
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.trusted_validation import (
    SYNTHETIC_PAPER_TRUST_TOKEN,
    PaperDay6TrustContext,
)

_PAPER_AUDIT_KIND = "paper_distribution"
_DAY6_PASS_STATUSES = {"pass", "accepted", "ok"}


def verify_paper_day6_trust(
    session: Session | None,
    request: PaperDistributionRequest,
    trust: PaperDay6TrustContext | None,
    *,
    execution_mode: TrustExecutionMode,
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

    if str(record.aggregate_status).lower() not in _DAY6_PASS_STATUSES:
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.validation_run_status")

    request_institution = (request.metadata_json or {}).get("institution_id")
    if (
        request_institution
        and record.institution_id
        and request_institution != record.institution_id
    ):
        issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
        paths.append("day6_trust.institution_mismatch")

    validated_ids = {
        str(entry.get("item_id"))
        for entry in (record.results_json or [])
        if entry.get("item_id")
    }
    if validated_ids:
        paper_ids = {item.item_id for item in request.items}
        if not paper_ids.issubset(validated_ids):
            issues.append(PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION)
            paths.append("day6_trust.item_coverage")

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

    version = request.target_policy_version or V1_POLICY_VERSION
    if session is None:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        paths.append("target_policy_version")
        return issues, paths

    try:
        registry = load_policy_registry(session, version=version)
    except Exception:
        issues.append(PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY)
        paths.append("target_policy_version")
        return issues, paths

    if not registry.rules:
        issues.append(PaperDistributionIssueCode.TARGET_INFEASIBLE)
        paths.append("target_policy_version")

    return issues, paths
