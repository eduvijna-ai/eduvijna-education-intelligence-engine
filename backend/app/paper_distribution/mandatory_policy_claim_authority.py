from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curator_auth.issuer import (
    CuratorAuthError,
    CuratorScope,
    attach_source_audit_event_to_durable_record,
    consume_decision_and_build_signed_payload,
    mark_durable_approval_revoked,
    verify_durable_curator_approval,
)
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.enums import (
    PolicyScopeType,
    SourceRevisionStatus,
    SourceStatus,
    SourceTrustTier,
    SourceType,
)
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision, policy_rule_source_revisions
from app.models.tenancy import Institution, Teacher
from app.paper_distribution.execution_context import PaperExecutionContext
from app.prerequisite_intelligence.authority import load_revision_record
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.root_cause_intelligence.mapping_evidence import (
    resolve_approved_source_span,
    source_content_checksum,
    verify_revision_content_integrity,
)
from app.source_intelligence.approval_fingerprint import (
    compute_revision_approval_fingerprint,
    verify_revision_stored_source_snapshot_checksum,
)

MANDATORY_POLICY_CLAIM_APPROVED_EVENT = "paper_mandatory_policy_claim_approved"
MANDATORY_POLICY_CLAIM_REVOKED_EVENT = "paper_mandatory_policy_claim_revoked"
PAPER_MANDATORY_POLICY_KEY = "paper_distribution_mandatory_targets"

_OFFICIAL_TRUST_TIERS = {
    SourceTrustTier.OFFICIAL_PRIMARY.value,
    SourceTrustTier.OFFICIAL_SUPPORTING.value,
}

_BOARD_MANDATORY_SOURCE_TYPES = frozenset(
    {
        SourceType.OFFICIAL_AUTHORITY.value,
        SourceType.OFFICIAL_SYLLABUS.value,
        SourceType.OFFICIAL_EXAM_BULLETIN.value,
        SourceType.MARKING_SCHEME.value,
    }
)


class MandatoryPolicyClaimAuthorityError(ValueError):
    pass


def _policy_value_checksum(value_json: dict[str, Any]) -> str:
    encoded = json.dumps(value_json, sort_keys=True, separators=(",", ":"))
    return stable_audit_ref("mandatory-policy-value", encoded)


def _rule_lifecycle_digest(rule: PolicyRule) -> str:
    payload = json.dumps(
        {
            "priority": int(rule.priority),
            "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
            "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
            "active": bool(rule.active),
            "metadata_checksum": stable_audit_ref(
                "mandatory-rule-metadata",
                json.dumps(rule.metadata_json or {}, sort_keys=True, separators=(",", ":")),
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("mandatory-rule-lifecycle", payload)


def mandatory_policy_claim_id(
    *,
    policy_rule_id: str,
    source_revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_checksum: str,
    rule_lifecycle_digest: str,
) -> str:
    payload = json.dumps(
        {
            "policy_rule_id": policy_rule_id,
            "source_revision_id": source_revision_id,
            "scope_type": scope_type,
            "scope_code": scope_code,
            "policy_key": policy_key,
            "value_checksum": value_checksum,
            "rule_lifecycle_digest": rule_lifecycle_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("mandatory-policy-claim", payload)


def mandatory_policy_approve_binding_payload(
    *,
    rule_id: str,
    revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_checksum: str,
    rule_lifecycle_digest: str,
    source_approval_fingerprint: str,
    source_snapshot_checksum: str,
    source_content_checksum: str,
    mandatory_source_locator: str,
    source_span_checksum: str,
) -> dict[str, Any]:
    return {
        "policy_rule_id": rule_id,
        "source_revision_id": revision_id,
        "scope_type": scope_type,
        "scope_code": scope_code,
        "policy_key": policy_key,
        "value_checksum": value_checksum,
        "rule_lifecycle_digest": rule_lifecycle_digest,
        "source_approval_fingerprint": source_approval_fingerprint,
        "source_snapshot_checksum": source_snapshot_checksum,
        "source_content_checksum": source_content_checksum,
        "mandatory_source_locator": mandatory_source_locator,
        "source_span_checksum": source_span_checksum,
    }


def compute_mandatory_policy_evidence_binding(
    session: Session,
    revision: SourceRevision,
    rule: PolicyRule,
) -> dict[str, str]:
    """Trusted source evidence at ticket issuance/consumption; fail-closed on tampering."""
    _revision_meets_mandatory_source_gate(session, revision)
    record = load_revision_record(session, revision.id)
    if record is None:
        raise MandatoryPolicyClaimAuthorityError("source revision record is missing")
    if not verify_revision_content_integrity(session, record):
        raise MandatoryPolicyClaimAuthorityError("source revision content integrity check failed")
    content_checksum = source_content_checksum(record)
    if not content_checksum:
        raise MandatoryPolicyClaimAuthorityError("source revision has no content checksum")
    locator = _mandatory_source_locator(rule)
    try:
        _, span_checksum = resolve_approved_source_span(session, record, locator)
    except ValueError as exc:
        raise MandatoryPolicyClaimAuthorityError(
            "mandatory policy source locator is not grounded in approved source"
        ) from exc
    return {
        "source_approval_fingerprint": str(revision.approval_fingerprint or ""),
        "source_snapshot_checksum": str(revision.source_snapshot_checksum or ""),
        "source_content_checksum": str(content_checksum),
        "mandatory_source_locator": locator,
        "source_span_checksum": span_checksum,
    }


def mandatory_policy_revoke_binding_payload(
    *,
    rule_id: str,
    revision_id: str,
    claim_id: str,
) -> dict[str, Any]:
    return {
        "policy_rule_id": rule_id,
        "source_revision_id": revision_id,
        "claim_id": claim_id,
    }


def curator_scope_for_policy_rule(
    rule: PolicyRule,
    *,
    organization_id: str,
    institution_id: str,
) -> CuratorScope:
    board_code = None
    teacher_id = None
    if str(rule.scope_type) == PolicyScopeType.BOARD.value:
        board_code = str(rule.scope_code)
    elif str(rule.scope_type) == PolicyScopeType.TEACHER.value:
        teacher_id = str(rule.scope_code)
    return CuratorScope(
        organization_id=str(organization_id),
        institution_id=str(institution_id),
        teacher_id=teacher_id,
        board_code=board_code,
    )


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


_MANDATORY_EVIDENCE_BINDING_KEYS = (
    "source_approval_fingerprint",
    "source_snapshot_checksum",
    "source_content_checksum",
    "mandatory_source_locator",
    "source_span_checksum",
)


def _revision_live_source_matches_approved_snapshot(revision: SourceRevision) -> bool:
    if not verify_revision_stored_source_snapshot_checksum(revision):
        return False
    snapshot = (revision.metadata_json or {}).get("source_snapshot")
    if not isinstance(snapshot, dict):
        return False
    source = revision.source
    if source is None:
        return False
    for field in (
        "board_or_exam",
        "source_type",
        "trust_tier",
        "authority",
        "academic_year",
    ):
        if str(snapshot.get(field) or "") != str(getattr(source, field, None) or ""):
            return False
    return True


def _mandatory_signed_evidence_still_valid(
    session: Session, revision: SourceRevision, payload: dict[str, Any]
) -> bool:
    record = load_revision_record(session, revision.id)
    if record is None:
        return False
    if not verify_revision_content_integrity(session, record):
        return False
    if not _revision_live_source_matches_approved_snapshot(revision):
        return False
    fingerprint = str(payload.get("source_approval_fingerprint") or "")
    if not fingerprint or fingerprint != str(revision.approval_fingerprint or ""):
        return False
    if fingerprint != compute_revision_approval_fingerprint(session, revision):
        return False
    content_checksum = source_content_checksum(record)
    if str(payload.get("source_content_checksum") or "") != str(content_checksum or ""):
        return False
    if str(payload.get("source_snapshot_checksum") or "") != str(
        revision.source_snapshot_checksum or ""
    ):
        return False
    locator = str(payload.get("mandatory_source_locator") or "").strip()
    span_checksum = str(payload.get("source_span_checksum") or "").strip()
    if not locator or not span_checksum:
        return False
    try:
        _, resolved_span = resolve_approved_source_span(session, record, locator)
    except ValueError:
        return False
    return resolved_span == span_checksum


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
    if not _revision_live_source_matches_approved_snapshot(revision):
        raise MandatoryPolicyClaimAuthorityError(
            "source authority metadata no longer matches approved snapshot"
        )
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
    raise MandatoryPolicyClaimAuthorityError(
        "legacy mandatory policy actor attestation is disabled; use authenticated curator decisions"
    )


def _mandatory_source_locator(rule: PolicyRule) -> str:
    meta = rule.metadata_json or {}
    locator = str(meta.get("mandatory_source_locator") or "").strip()
    if not locator:
        raise MandatoryPolicyClaimAuthorityError("mandatory_source_locator is required on rule")
    return locator


def _verify_scope_source_trust(
    session: Session, rule: PolicyRule, revision: SourceRevision
) -> None:
    source = revision.source
    if source is None:
        raise MandatoryPolicyClaimAuthorityError("source revision has no source")
    scope_type = str(rule.scope_type)
    trust = str(source.trust_tier or "")
    if scope_type == PolicyScopeType.BOARD.value:
        if trust not in _OFFICIAL_TRUST_TIERS:
            raise MandatoryPolicyClaimAuthorityError(
                "board mandatory policy requires official source trust tier"
            )
        source_type = str(source.source_type or "")
        if source_type not in _BOARD_MANDATORY_SOURCE_TYPES:
            raise MandatoryPolicyClaimAuthorityError(
                "board mandatory policy requires an official authority source type"
            )
        board_ref = str(source.board_or_exam or "").strip().lower()
        scope_board = str(rule.scope_code or "").strip().lower()
        if not board_ref or not scope_board or board_ref != scope_board:
            raise MandatoryPolicyClaimAuthorityError(
                "mandatory policy board scope does not match source board authority"
            )
        locator = _mandatory_source_locator(rule)
        from app.prerequisite_intelligence.authority import load_revision_record

        record = load_revision_record(session, revision.id)
        if record is None:
            raise MandatoryPolicyClaimAuthorityError("source revision record is missing")
        try:
            resolve_approved_source_span(session, record, locator)
        except ValueError as exc:
            raise MandatoryPolicyClaimAuthorityError(
                "mandatory policy source locator is not grounded in approved source"
            ) from exc
        return


def _institution_board_code(session: Session, institution_id: str | None) -> str | None:
    if not institution_id:
        return None
    institution = session.get(Institution, institution_id)
    if institution is None:
        return None
    board_code = (institution.metadata_json or {}).get("board_code")
    return str(board_code).strip() if board_code else None


def _policy_claim_applies_to_execution_context(
    session: Session,
    rule: PolicyRule,
    execution_context: PaperExecutionContext | None,
) -> bool:
    if execution_context is None or not execution_context.institution_id:
        return False
    institution = session.get(Institution, execution_context.institution_id)
    if institution is None or not institution.active:
        return False
    scope_type = str(rule.scope_type)
    scope_code = str(rule.scope_code)
    if str(execution_context.organization_id or "").strip():
        if str(institution.organization_id) != str(execution_context.organization_id).strip():
            return False
    if scope_type == PolicyScopeType.BOARD.value:
        inst_board = _institution_board_code(session, execution_context.institution_id)
        if not inst_board:
            return False
        if execution_context.board_code and str(
            execution_context.board_code
        ).strip().lower() != inst_board.lower():
            return False
        return scope_code.lower() == inst_board.lower()
    if scope_type == PolicyScopeType.INSTITUTION.value:
        return scope_code in {institution.id, institution.code}
    if scope_type == PolicyScopeType.TEACHER.value:
        teacher_id = str(execution_context.teacher_id or "").strip()
        if not teacher_id:
            return False
        teacher = session.get(Teacher, teacher_id)
        if teacher is None:
            teacher = session.scalar(
                select(Teacher).where(
                    Teacher.institution_id == execution_context.institution_id,
                    Teacher.external_code == teacher_id,
                )
            )
        if teacher is None or not teacher.active:
            return False
        if str(teacher.institution_id) != str(execution_context.institution_id):
            return False
        return scope_code in {str(teacher.id), str(teacher.external_code)}
    return False


def curator_expected_scope_for_execution(
    session: Session,
    rule: PolicyRule,
    execution_context: PaperExecutionContext,
) -> CuratorScope:
    organization_id = str(execution_context.organization_id or "").strip()
    institution_id = str(execution_context.institution_id or "").strip()
    if not organization_id and institution_id:
        institution = session.get(Institution, institution_id)
        if institution is not None:
            organization_id = str(institution.organization_id)
    scope_type = str(rule.scope_type)
    if scope_type == PolicyScopeType.BOARD.value:
        return CuratorScope(
            organization_id=organization_id,
            institution_id="",
            board_code=str(rule.scope_code),
        )
    if scope_type == PolicyScopeType.INSTITUTION.value:
        return CuratorScope(
            organization_id=organization_id,
            institution_id=institution_id,
        )
    teacher_id = None
    if scope_type == PolicyScopeType.TEACHER.value:
        teacher_id = str(rule.scope_code)
    return CuratorScope(
        organization_id=organization_id,
        institution_id=institution_id,
        teacher_id=teacher_id,
    )


def _rule_effective_on(rule: PolicyRule, on_date: date | None = None) -> bool:
    effective = on_date or date.today()
    if rule.effective_from is not None and rule.effective_from > effective:
        return False
    if rule.effective_to is not None and rule.effective_to < effective:
        return False
    return True


def _claim_payload_matches_rule(rule: PolicyRule, payload: dict[str, Any]) -> bool:
    if str(payload.get("policy_rule_id") or "") != str(rule.id):
        return False
    if str(payload.get("scope_type") or "") != str(rule.scope_type):
        return False
    if str(payload.get("scope_code") or "") != str(rule.scope_code):
        return False
    if str(payload.get("policy_key") or "") != str(rule.policy_key):
        return False
    value_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    if str(payload.get("value_checksum") or "") != value_checksum:
        return False
    lifecycle = _rule_lifecycle_digest(rule)
    if str(payload.get("rule_lifecycle_digest") or "") != lifecycle:
        return False
    raw_priority = payload.get("rule_priority")
    if raw_priority is None:
        return False
    if int(raw_priority) != int(rule.priority):
        return False
    return True


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
    organization_id: str,
    institution_id: str,
    curator_decision_token: str,
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
    _verify_scope_source_trust(session, rule, revision)
    if not _rule_effective_on(rule):
        raise MandatoryPolicyClaimAuthorityError("policy rule is not effective")
    enforcement = str((rule.metadata_json or {}).get("enforcement") or "mandatory")
    if enforcement == "weaken":
        raise MandatoryPolicyClaimAuthorityError(
            "weakening mandatory distribution targets is not authorized for signed approval"
        )

    record = load_revision_record(session, revision_id)
    if record is None:
        raise MandatoryPolicyClaimAuthorityError("source revision record is missing")
    if not verify_revision_content_integrity(session, record):
        raise MandatoryPolicyClaimAuthorityError("source revision content integrity check failed")
    content_checksum = source_content_checksum(record)
    if not content_checksum:
        raise MandatoryPolicyClaimAuthorityError("source revision has no content checksum")
    locator = _mandatory_source_locator(rule)
    try:
        _, span_checksum = resolve_approved_source_span(session, record, locator)
    except ValueError as exc:
        raise MandatoryPolicyClaimAuthorityError(
            "mandatory policy source locator is not grounded in approved source"
        ) from exc

    value_checksum = submitted_checksum
    lifecycle = _rule_lifecycle_digest(rule)
    evidence = compute_mandatory_policy_evidence_binding(session, revision, rule)
    binding = mandatory_policy_approve_binding_payload(
        rule_id=rule_id,
        revision_id=revision_id,
        scope_type=scope_type,
        scope_code=scope_code,
        policy_key=policy_key,
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
        **evidence,
    )
    scope = curator_scope_for_policy_rule(
        rule, organization_id=organization_id, institution_id=institution_id
    )
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=rule_id,
        source_revision_id=revision_id,
        scope_type=scope_type,
        scope_code=scope_code,
        policy_key=policy_key,
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
    )
    try:
        claim_body = {
            "claim_id": claim_id,
            "policy_rule_id": rule_id,
            "source_revision_id": revision_id,
            "scope_type": scope_type,
            "scope_code": scope_code,
            "policy_key": policy_key,
            "value_checksum": value_checksum,
            "rule_lifecycle_digest": lifecycle,
            "rule_priority": int(rule.priority),
            "effective_from": (
                rule.effective_from.isoformat() if rule.effective_from else None
            ),
            "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
            "mandatory_source_locator": locator,
            "source_approval_fingerprint": str(revision.approval_fingerprint or ""),
            "source_content_checksum": content_checksum,
            "source_span_checksum": span_checksum,
            "source_snapshot_checksum": str(revision.source_snapshot_checksum or ""),
            "approved_by": "",
            "claim_status": "active",
        }
        signed_payload = consume_decision_and_build_signed_payload(
            session,
            token=curator_decision_token,
            role=CuratorRole.MANDATORY_POLICY_CURATOR,
            operation=CuratorOperation.MANDATORY_POLICY_APPROVE,
            binding_payload={**binding, "claim_id": claim_id},
            scope=scope,
            claim_body=claim_body,
            claim_id=claim_id,
        )
    except CuratorAuthError as exc:
        raise MandatoryPolicyClaimAuthorityError(str(exc)) from exc
    policy_actor = str(signed_payload.get("approved_by") or "").strip()
    if not policy_actor:
        policy_actor = str(
            (signed_payload.get("curator_approval") or {}).get("admin_external_code") or ""
        ).strip()
    if policy_actor != str(actor_id).strip():
        raise MandatoryPolicyClaimAuthorityError("mandatory policy actor mismatch")
    audit_event = SourceAuditEvent(
        source_id=revision.source_id,
        source_revision_id=revision_id,
        event_type=MANDATORY_POLICY_CLAIM_APPROVED_EVENT,
        actor_id=actor_id,
        request_id=request_id,
        outcome="success",
        payload_json=signed_payload,
    )
    session.add(audit_event)
    session.flush()
    approval_jti = str((signed_payload.get("curator_approval") or {}).get("jti") or "")
    if approval_jti:
        attach_source_audit_event_to_durable_record(
            session,
            decision_jti=approval_jti,
            source_audit_event_id=audit_event.id,
        )
    session.flush()
    return claim_id


def revoke_mandatory_policy_claim(
    session: Session,
    *,
    rule_id: str,
    revision_id: str,
    claim_id: str,
    actor_id: str,
    organization_id: str,
    institution_id: str,
    curator_decision_token: str,
    request_id: str | None = None,
) -> None:
    rule = session.get(PolicyRule, rule_id)
    if rule is None:
        raise MandatoryPolicyClaimAuthorityError("policy rule is unknown")
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        raise MandatoryPolicyClaimAuthorityError("source revision is unknown")
    scope = curator_scope_for_policy_rule(
        rule, organization_id=organization_id, institution_id=institution_id
    )
    binding = mandatory_policy_revoke_binding_payload(
        rule_id=rule_id, revision_id=revision_id, claim_id=claim_id
    )
    try:
        signed_payload = consume_decision_and_build_signed_payload(
            session,
            token=curator_decision_token,
            role=CuratorRole.MANDATORY_POLICY_CURATOR,
            operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
            binding_payload=binding,
            scope=scope,
            claim_body={
                "claim_id": claim_id,
                "claim_status": "revoked",
                "approved_by": "",
            },
            claim_id=claim_id,
        )
    except CuratorAuthError as exc:
        raise MandatoryPolicyClaimAuthorityError(str(exc)) from exc
    revoke_actor = str(signed_payload.get("approved_by") or "").strip()
    if not revoke_actor:
        revoke_actor = str(
            (signed_payload.get("curator_approval") or {}).get("admin_external_code") or ""
        ).strip()
    if revoke_actor != str(actor_id).strip():
        raise MandatoryPolicyClaimAuthorityError("mandatory policy revoke actor mismatch")
    revoke_event = SourceAuditEvent(
        source_id=revision.source_id,
        source_revision_id=revision_id,
        event_type=MANDATORY_POLICY_CLAIM_REVOKED_EVENT,
        actor_id=actor_id,
        request_id=request_id,
        outcome="success",
        payload_json=signed_payload,
    )
    session.add(revoke_event)
    session.flush()
    mark_durable_approval_revoked(session, claim_id=claim_id)
    revoke_jti = str((signed_payload.get("curator_approval") or {}).get("jti") or "")
    if revoke_jti:
        attach_source_audit_event_to_durable_record(
            session,
            decision_jti=revoke_jti,
            source_audit_event_id=revoke_event.id,
        )
    session.flush()


def mandatory_policy_claim_active(
    session: Session,
    *,
    rule_id: str,
    revision_id: str,
    scope_type: str,
    scope_code: str,
    policy_key: str,
    value_json: dict[str, Any],
    organization_id: str,
    institution_id: str,
    execution_context: PaperExecutionContext | None = None,
) -> bool:
    rule = session.get(PolicyRule, rule_id)
    if rule is None or not rule.active or not _rule_effective_on(rule):
        return False
    if not _policy_claim_applies_to_execution_context(session, rule, execution_context):
        return False
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return False
    try:
        _revision_meets_mandatory_source_gate(session, revision)
        _verify_scope_source_trust(session, rule, revision)
    except MandatoryPolicyClaimAuthorityError:
        return False
    if not _revision_linked_to_rule(session, rule_id=str(rule.id), revision_id=revision_id):
        return False

    value_checksum = _policy_value_checksum(value_json)
    lifecycle = _rule_lifecycle_digest(rule)
    claim_id = mandatory_policy_claim_id(
        policy_rule_id=rule_id,
        source_revision_id=revision_id,
        scope_type=scope_type,
        scope_code=scope_code,
        policy_key=policy_key,
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
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
        if not _claim_payload_matches_rule(rule, payload):
            continue
        if not _mandatory_signed_evidence_still_valid(session, revision, payload):
            continue
        binding = mandatory_policy_approve_binding_payload(
            rule_id=rule_id,
            revision_id=revision_id,
            scope_type=scope_type,
            scope_code=scope_code,
            policy_key=policy_key,
            value_checksum=value_checksum,
            rule_lifecycle_digest=lifecycle,
            source_approval_fingerprint=str(payload.get("source_approval_fingerprint") or ""),
            source_snapshot_checksum=str(payload.get("source_snapshot_checksum") or ""),
            source_content_checksum=str(payload.get("source_content_checksum") or ""),
            mandatory_source_locator=str(payload.get("mandatory_source_locator") or ""),
            source_span_checksum=str(payload.get("source_span_checksum") or ""),
        )
        binding = {**binding, "claim_id": claim_id}
        expected_scope = None
        if execution_context is not None and execution_context.institution_id:
            expected_scope = curator_expected_scope_for_execution(
                session, rule, execution_context
            )
        if not verify_durable_curator_approval(
            session,
            payload,
            role=CuratorRole.MANDATORY_POLICY_CURATOR,
            operation=CuratorOperation.MANDATORY_POLICY_APPROVE,
            binding_payload=binding,
            expected_scope=expected_scope,
            source_audit_event_id=event.id,
            audit_actor_id=str(event.actor_id or ""),
        ):
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
            rev_payload = rev.payload_json or {}
            if str(rev_payload.get("claim_id") or "") != claim_id:
                continue
            revoke_binding = mandatory_policy_revoke_binding_payload(
                rule_id=rule_id, revision_id=revision_id, claim_id=claim_id
            )
            if verify_durable_curator_approval(
                session,
                rev_payload,
                role=CuratorRole.MANDATORY_POLICY_CURATOR,
                operation=CuratorOperation.MANDATORY_POLICY_REVOKE,
                binding_payload=revoke_binding,
                source_audit_event_id=rev.id,
                audit_actor_id=str(rev.actor_id or ""),
            ):
                return False
        return True
    return False
