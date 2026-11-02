from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import SourceAuditEvent, SourceRevision
from app.prerequisite_intelligence.stable_ids import stable_audit_ref

MANDATORY_POLICY_CLAIM_APPROVED_EVENT = "paper_mandatory_policy_claim_approved"
MANDATORY_POLICY_CLAIM_REVOKED_EVENT = "paper_mandatory_policy_claim_revoked"


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
    revision = session.get(SourceRevision, revision_id)
    if revision is None or revision.source is None:
        raise MandatoryPolicyClaimAuthorityError("source revision is unknown")
    value_checksum = _policy_value_checksum(value_json)
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
