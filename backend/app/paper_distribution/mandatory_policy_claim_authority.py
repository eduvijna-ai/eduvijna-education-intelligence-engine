from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PolicyScopeType, SourceRevisionStatus, SourceStatus, SourceTrustTier
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision, policy_rule_source_revisions
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.source_intelligence.approval_fingerprint import compute_revision_approval_fingerprint

MANDATORY_POLICY_CLAIM_APPROVED_EVENT = "paper_mandatory_policy_claim_approved"
MANDATORY_POLICY_CLAIM_REVOKED_EVENT = "paper_mandatory_policy_claim_revoked"
PAPER_MANDATORY_POLICY_KEY = "paper_distribution_mandatory_targets"

_OFFICIAL_TRUST_TIERS = {
    SourceTrustTier.OFFICIAL_PRIMARY.value,
    SourceTrustTier.OFFICIAL_SUPPORTING.value,
}


class MandatoryPolicyClaimAuthorityError(ValueError):
    pass


def mandatory_policy_claim_id(
    *,
    policy_rule_id: str,
    source_revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_checksum: str,
) -> str:
    payload = json.dumps(
        {
            "policy_rule_id": policy_rule_id,
            "source_revision_id": source_revision_id,
            "scope_type": scope_type,
            "scope_code": scope_code,
            "policy_key": policy_key,
            "value_checksum": value_checksum,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("mandatory-policy-claim", payload)


def _policy_value_checksum(value_json: dict[str, Any]) -> str:
    encoded = json.dumps(value_json, sort_keys=True, separators=(",", ":"))
    return stable_audit_ref("mandatory-policy-value", encoded)


def _latest_source_approved_audit(
    session: Session, revision_id: str
) -> SourceAuditEvent | None:
    return session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )


def _revision_linked_to_rule(session: Session, *, rule_id: str, revision_id: str) -> bool:
    linked = session.scalar(
        select(policy_rule_source_revisions.c.source_revision_id).where(
            policy_rule_source_revisions.c.policy_rule_id == rule_id,
            policy_rule_source_revisions.c.source_revision_id == revision_id,
        )
    )
    return linked is not None


def _revision_meets_mandatory_source_gate(session: Session, revision: SourceRevision) -> None:
    source = revision.source
    if source is None:
        raise MandatoryPolicyClaimAuthorityError("source revision has no source")
    if source.status != SourceStatus.ACTIVE.value:
        raise MandatoryPolicyClaimAuthorityError("source is not active")
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        raise MandatoryPolicyClaimAuthorityError("source revision is not active")
    if not revision.approval_fingerprint or not revision.approved_by:
        raise MandatoryPolicyClaimAuthorityError("source revision is not approved")
    approved = _latest_source_approved_audit(session, revision.id)
    if approved is None:
        raise MandatoryPolicyClaimAuthorityError("source revision lacks source_approved audit")
    audit_fingerprint = str((approved.payload_json or {}).get("approval_fingerprint") or "")
    if audit_fingerprint != str(revision.approval_fingerprint):
        raise MandatoryPolicyClaimAuthorityError("source approval fingerprint mismatch")
    if compute_revision_approval_fingerprint(session, revision) != str(
        revision.approval_fingerprint
    ):
        raise MandatoryPolicyClaimAuthorityError("source approval fingerprint stale")


def _verify_mandatory_claim_actor(
    session: Session,
    *,
    rule: PolicyRule,
    revision: SourceRevision,
    actor_id: str,
) -> None:
    if not actor_id.strip():
        raise MandatoryPolicyClaimAuthorityError("actor_id is required")
    approved_by = str(revision.approved_by or "").strip()
    rule_meta = rule.metadata_json or {}
    allowed = {str(item) for item in rule_meta.get("mandatory_claim_approver_actor_ids") or []}
    if approved_by:
        allowed.add(approved_by)
    if actor_id not in allowed:
        raise MandatoryPolicyClaimAuthorityError("actor is not authorized for mandatory claim")


def _verify_scope_source_trust(rule: PolicyRule, revision: SourceRevision) -> None:
    source = revision.source
    if source is None:
        raise MandatoryPolicyClaimAuthorityError("source revision has no source")
    scope_type = str(rule.scope_type)
    trust = str(source.trust_tier or "")
    if scope_type == PolicyScopeType.BOARD.value and trust not in _OFFICIAL_TRUST_TIERS:
        raise MandatoryPolicyClaimAuthorityError(
            "board mandatory policy requires official source trust tier"
        )


def approve_mandatory_policy_claim(
    session: Session,
    *,
    rule_id: str,
    revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_json: dict[str, Any],
    actor_id: str,
    request_id: str | None = None,
) -> str:
    rule = session.get(PolicyRule, rule_id)
    if rule is None or not rule.active:
        raise MandatoryPolicyClaimAuthorityError("policy rule is unknown or inactive")
    if str(rule.scope_type) != str(scope_type):
        raise MandatoryPolicyClaimAuthorityError("policy scope_type mismatch")
    if str(rule.scope_code) != str(scope_code):
        raise MandatoryPolicyClaimAuthorityError("policy scope_code mismatch")
    if str(rule.policy_key) != str(policy_key):
        raise MandatoryPolicyClaimAuthorityError("policy_key mismatch")
    if policy_key != PAPER_MANDATORY_POLICY_KEY:
        raise MandatoryPolicyClaimAuthorityError("unsupported mandatory policy key")
    rule_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    submitted_checksum = _policy_value_checksum(value_json)
    if rule_checksum != submitted_checksum:
        raise MandatoryPolicyClaimAuthorityError("policy value_json does not match persisted rule")
    if not _revision_linked_to_rule(session, rule_id=str(rule.id), revision_id=revision_id):
        raise MandatoryPolicyClaimAuthorityError("source revision is not bound to policy rule")

    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        raise MandatoryPolicyClaimAuthorityError("source revision is unknown")
    _revision_meets_mandatory_source_gate(session, revision)
    _verify_scope_source_trust(rule, revision)
    _verify_mandatory_claim_actor(session, rule=rule, revision=revision, actor_id=actor_id)

    value_checksum = submitted_checksum
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=rule_id,
        source_revision_id=revision_id,
        scope_type=scope_type,
        scope_code=scope_code,
        policy_key=policy_key,
        value_checksum=value_checksum,
    )
    session.add(
        SourceAuditEvent(
            source_id=revision.source_id,
            source_revision_id=revision_id,
            event_type=MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            actor_id=actor_id,
            request_id=request_id,
            outcome="success",
            payload_json={
                "claim_id": claim_id,
                "policy_rule_id": rule_id,
                "scope_type": scope_type,
                "scope_code": scope_code,
                "policy_key": policy_key,
                "value_checksum": value_checksum,
                "approved_by": actor_id,
                "claim_status": "active",
            },
        )
    )
    session.flush()
    return claim_id


def mandatory_policy_claim_active(
    session: Session,
    *,
    rule_id: str,
    revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_json: dict[str, Any],
) -> bool:
    value_checksum = _policy_value_checksum(value_json)
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=rule_id,
        source_revision_id=revision_id,
        scope_type=scope_type,
        scope_code=scope_code,
        policy_key=policy_key,
        value_checksum=value_checksum,
    )
    events = session.scalars(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    ).all()
    for event in events:
        payload = event.payload_json or {}
        if str(payload.get("claim_id") or "") != claim_id:
            continue
        if str(payload.get("policy_rule_id") or "") != rule_id:
            continue
        revoked = session.scalars(
            select(SourceAuditEvent).where(
                SourceAuditEvent.source_revision_id == revision_id,
                SourceAuditEvent.event_type == MANDATORY_POLICY_CLAIM_REVOKED_EVENT,
                SourceAuditEvent.outcome == "success",
            )
        ).all()
        for rev in revoked:
            if rev.created_at <= event.created_at:
                continue
            if str((rev.payload_json or {}).get("claim_id") or "") == claim_id:
                return False
        return True
    return False
