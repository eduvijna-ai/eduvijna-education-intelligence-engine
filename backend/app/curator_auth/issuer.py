from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.curator_auth import (
    CuratorDecisionNonce,
    CuratorDurableApprovalRecord,
    CuratorOperatorCredential,
)
from app.models.tenancy import AdminActor, Institution, Organization, Teacher
from app.prerequisite_intelligence.stable_ids import stable_audit_ref

UNSAFE_CURATOR_SIGNING_KEYS = frozenset(
    {
        "",
        "local-development-only",
        "change-me-for-non-local-use",
    }
)

MIN_SIGNING_KEY_BYTES = 32
MIN_DECISION_TTL_SECONDS = 1
MAX_DECISION_TTL_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 30
DURABLE_APPROVAL_VERSION = 2

_DURABLE_APPROVAL_OPERATIONS = frozenset(
    {
        CuratorOperation.MAPPING_APPROVE.value,
        CuratorOperation.MANDATORY_POLICY_APPROVE.value,
    }
)
_DURABLE_REVOCATION_OPERATIONS = frozenset(
    {
        CuratorOperation.MAPPING_REVOKE.value,
        CuratorOperation.MANDATORY_POLICY_REVOKE.value,
    }
)

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class CuratorAuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CuratorScope:
    organization_id: str
    institution_id: str
    curriculum_version_id: str | None = None
    teacher_id: str | None = None
    board_code: str | None = None


@dataclass(frozen=True, slots=True)
class _ConsumedCuratorDecision:
    admin_actor_id: str
    admin_actor_external_code: str
    role: CuratorRole
    operation: CuratorOperation
    binding_digest: str
    scope: CuratorScope
    jti: str
    key_id: str
    issued_at: int


def _require_signing_key() -> tuple[str, str]:
    settings = get_settings()
    key = (settings.curator_approval_signing_key or "").strip()
    key_id = (settings.curator_approval_signing_key_id or "curator-approval-v1").strip()
    if not key or key in UNSAFE_CURATOR_SIGNING_KEYS:
        raise CuratorAuthError("curator approval signing key is not configured")
    if len(key.encode("utf-8")) < MIN_SIGNING_KEY_BYTES:
        raise CuratorAuthError("curator approval signing key is too short")
    if key == settings.api_secret_key:
        raise CuratorAuthError("curator approval signing key must not equal API secret")
    return key_id, key


_CLAIM_ID_EXCLUDED_FROM_BINDING_DIGEST = frozenset(
    {
        CuratorOperation.MAPPING_APPROVE.value,
        CuratorOperation.MANDATORY_POLICY_APPROVE.value,
    }
)


def operation_binding_digest(operation: str, payload: dict[str, Any]) -> str:
    cleaned = dict(payload)
    if operation in _CLAIM_ID_EXCLUDED_FROM_BINDING_DIGEST:
        cleaned = {key: value for key, value in cleaned.items() if key != "claim_id"}
    encoded = json.dumps(
        {"operation": operation, **cleaned},
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("curator-operation-binding", encoded)


def hash_operator_secret(plaintext: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        plaintext.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return {
        "algorithm": "scrypt",
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "hash_b64": base64.b64encode(digest).decode("ascii"),
        "n": str(SCRYPT_N),
        "r": str(SCRYPT_R),
        "p": str(SCRYPT_P),
    }


def verify_operator_secret(plaintext: str, stored: dict[str, str]) -> bool:
    if stored.get("algorithm") != "scrypt":
        return False
    try:
        salt = base64.b64decode(str(stored.get("salt_b64") or ""))
        expected = base64.b64decode(str(stored.get("hash_b64") or ""))
        n = int(stored.get("n") or SCRYPT_N)
        r = int(stored.get("r") or SCRYPT_R)
        p = int(stored.get("p") or SCRYPT_P)
    except (ValueError, TypeError):
        return False
    actual = hashlib.scrypt(
        plaintext.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)


def _scope_dict(scope: CuratorScope) -> dict[str, str | None]:
    return {
        "organization_id": scope.organization_id,
        "institution_id": scope.institution_id,
        "curriculum_version_id": scope.curriculum_version_id,
        "teacher_id": scope.teacher_id,
        "board_code": scope.board_code,
    }


def _resolve_teacher_in_scope(session: Session, scope: CuratorScope) -> Teacher | None:
    if not scope.teacher_id:
        return None
    teacher = session.get(Teacher, scope.teacher_id)
    if teacher is not None:
        return teacher
    return session.scalar(
        select(Teacher).where(
            Teacher.institution_id == scope.institution_id,
            Teacher.external_code == str(scope.teacher_id),
        )
    )


def _assert_tenant_scope_active(session: Session, scope: CuratorScope) -> None:
    org = session.get(Organization, scope.organization_id)
    if org is None or not org.active:
        raise CuratorAuthError("curator scope organization is not active")
    inst = session.get(Institution, scope.institution_id)
    if inst is None or not inst.active:
        raise CuratorAuthError("curator scope institution is not active")
    if str(inst.organization_id) != str(scope.organization_id):
        raise CuratorAuthError("curator scope institution organization mismatch")
    if scope.board_code:
        meta_board = (inst.metadata_json or {}).get("board_code")
        if not meta_board or str(meta_board).strip().lower() != str(
            scope.board_code
        ).strip().lower():
            raise CuratorAuthError("curator scope board mismatch with institution metadata")
    if scope.teacher_id:
        teacher = _resolve_teacher_in_scope(session, scope)
        if teacher is None or not teacher.active:
            raise CuratorAuthError("curator scope teacher is not active")
        if str(teacher.institution_id) != str(scope.institution_id):
            raise CuratorAuthError("curator scope teacher institution mismatch")


def _scope_matches_credential(
    session: Session,
    credential: CuratorOperatorCredential,
    scope: CuratorScope,
) -> bool:
    if credential.organization_id and str(credential.organization_id) != str(
        scope.organization_id
    ):
        return False
    if credential.institution_id and str(credential.institution_id) != str(
        scope.institution_id
    ):
        return False
    if credential.teacher_id:
        if not scope.teacher_id:
            return False
        cred_teacher = session.get(Teacher, credential.teacher_id)
        scope_teacher = _resolve_teacher_in_scope(session, scope)
        if cred_teacher is None or scope_teacher is None:
            return False
        if str(cred_teacher.id) != str(scope_teacher.id):
            return False
    elif scope.teacher_id:
        return False
    if credential.curriculum_version_id:
        if not scope.curriculum_version_id or str(credential.curriculum_version_id) != str(
            scope.curriculum_version_id
        ):
            return False
    if scope.board_code:
        if not credential.board_scope_authorized:
            return False
        if not credential.board_code or str(credential.board_code) != str(scope.board_code):
            return False
    return True


def verify_curator_operator(
    session: Session,
    *,
    admin_external_code: str,
    operator_secret: str,
    role: CuratorRole,
    scope: CuratorScope,
) -> AdminActor:
    _assert_tenant_scope_active(session, scope)
    admin = session.scalar(
        select(AdminActor).where(
            AdminActor.external_code == str(admin_external_code).strip(),
            AdminActor.active.is_(True),
        )
    )
    if admin is None:
        raise CuratorAuthError("curator admin actor is not active")
    if scope.organization_id and (
        not admin.organization_id
        or str(admin.organization_id) != str(scope.organization_id)
    ):
        raise CuratorAuthError("curator scope organization mismatch")
    if scope.institution_id and (
        not admin.institution_id or str(admin.institution_id) != str(scope.institution_id)
    ):
        raise CuratorAuthError("curator scope institution mismatch")
    credential = session.scalar(
        select(CuratorOperatorCredential).where(
            CuratorOperatorCredential.admin_actor_id == admin.id,
            CuratorOperatorCredential.role == role.value,
            CuratorOperatorCredential.active.is_(True),
        )
    )
    if credential is None:
        raise CuratorAuthError("curator operator credential is not provisioned")
    if not _scope_matches_credential(session, credential, scope):
        raise CuratorAuthError("curator credential scope mismatch")
    if not verify_operator_secret(operator_secret, credential.credential_hash_json):
        raise CuratorAuthError("curator operator credential verification failed")
    return admin


def _encode_token(payload: dict[str, Any], signing_key: str) -> str:
    body = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(
        signing_key.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{body}.{sig_b64}"


def _decode_token(token: str, signing_key: str) -> dict[str, Any]:
    parts = str(token).split(".", 1)
    if len(parts) != 2:
        raise CuratorAuthError("curator decision token is malformed")
    body, sig_b64 = parts
    pad = "=" * (-len(body) % 4)
    expected = hmac.new(
        signing_key.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        actual = base64.urlsafe_b64decode(sig_b64 + ("=" * (-len(sig_b64) % 4)))
    except ValueError as exc:
        raise CuratorAuthError("curator decision token signature is invalid") from exc
    if not hmac.compare_digest(expected, actual):
        raise CuratorAuthError("curator decision token signature is invalid")
    payload = json.loads(base64.urlsafe_b64decode(body + pad).decode("utf-8"))
    if not isinstance(payload, dict):
        raise CuratorAuthError("curator decision token payload is invalid")
    return payload


def _clamp_ttl(ttl_seconds: int) -> int:
    return max(MIN_DECISION_TTL_SECONDS, min(int(ttl_seconds), MAX_DECISION_TTL_SECONDS))


def issue_curator_write_decision(
    session: Session,
    *,
    admin_external_code: str,
    operator_secret: str,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    scope: CuratorScope,
    ttl_seconds: int = 300,
) -> str:
    key_id, signing_key = _require_signing_key()
    admin = verify_curator_operator(
        session,
        admin_external_code=admin_external_code,
        operator_secret=operator_secret,
        role=role,
        scope=scope,
    )
    binding_digest = operation_binding_digest(operation.value, binding_payload)
    now = datetime.now(tz=UTC)
    ttl = _clamp_ttl(ttl_seconds)
    exp = now + timedelta(seconds=ttl)
    jti = str(uuid.uuid4())
    payload = {
        "v": 1,
        "kid": key_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "admin_actor_id": admin.id,
        "admin_external_code": admin.external_code,
        "role": role.value,
        "operation": operation.value,
        "binding_digest": binding_digest,
        "scope": _scope_dict(scope),
    }
    token = _encode_token(payload, signing_key)
    session.add(
        CuratorDecisionNonce(
            jti=jti,
            expires_at_iso=exp.isoformat(),
        )
    )
    session.flush()
    return token


def _consume_curator_write_decision(
    session: Session,
    *,
    token: str,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    scope: CuratorScope,
) -> _ConsumedCuratorDecision:
    key_id, signing_key = _require_signing_key()
    payload = _decode_token(token, signing_key)
    if int(payload.get("v") or 0) != 1:
        raise CuratorAuthError("unsupported curator decision token version")
    if str(payload.get("kid") or "") != key_id:
        raise CuratorAuthError("curator decision signing key id mismatch")
    if str(payload.get("role") or "") != role.value:
        raise CuratorAuthError("curator decision role mismatch")
    if str(payload.get("operation") or "") != operation.value:
        raise CuratorAuthError("curator decision operation mismatch")
    expected_binding = operation_binding_digest(operation.value, binding_payload)
    if str(payload.get("binding_digest") or "") != expected_binding:
        raise CuratorAuthError("curator decision binding mismatch")
    scope_payload = payload.get("scope") or {}
    if not isinstance(scope_payload, dict):
        raise CuratorAuthError("curator decision scope is invalid")
    for field in ("organization_id", "institution_id"):
        if str(scope_payload.get(field) or "") != str(getattr(scope, field)):
            raise CuratorAuthError("curator decision scope mismatch")
    for optional_field in ("curriculum_version_id", "teacher_id", "board_code"):
        req_val = getattr(scope, optional_field)
        if req_val is not None:
            if str(scope_payload.get(optional_field) or "") != str(req_val):
                raise CuratorAuthError("curator decision scope mismatch")
    iat = int(payload.get("iat") or 0)
    now_ts = datetime.now(tz=UTC).timestamp()
    if iat > now_ts + MAX_CLOCK_SKEW_SECONDS:
        raise CuratorAuthError("curator decision token issued in the future")
    exp = int(payload.get("exp") or 0)
    if now_ts > exp + MAX_CLOCK_SKEW_SECONDS:
        raise CuratorAuthError("curator decision token expired")
    jti = str(payload.get("jti") or "").strip()
    if not jti:
        raise CuratorAuthError("curator decision token missing jti")
    nonce = session.scalar(
        select(CuratorDecisionNonce).where(CuratorDecisionNonce.jti == jti)
    )
    if nonce is None:
        raise CuratorAuthError("curator decision jti is unknown or already consumed")
    try:
        expires_at = datetime.fromisoformat(str(nonce.expires_at_iso))
    except ValueError as exc:
        raise CuratorAuthError("curator decision nonce expiry is invalid") from exc
    if now_ts > expires_at.timestamp() + MAX_CLOCK_SKEW_SECONDS:
        raise CuratorAuthError("curator decision token expired")
    session.delete(nonce)
    session.flush()
    admin_id = str(payload.get("admin_actor_id") or "").strip()
    admin = session.get(AdminActor, admin_id)
    if admin is None or not admin.active:
        raise CuratorAuthError("curator decision admin actor is not active")
    if scope.organization_id and (
        not admin.organization_id or str(admin.organization_id) != str(scope.organization_id)
    ):
        raise CuratorAuthError("curator decision admin organization mismatch")
    if scope.institution_id and (
        not admin.institution_id or str(admin.institution_id) != str(scope.institution_id)
    ):
        raise CuratorAuthError("curator decision admin institution mismatch")
    _assert_tenant_scope_active(session, scope)
    credential = session.scalar(
        select(CuratorOperatorCredential).where(
            CuratorOperatorCredential.admin_actor_id == admin.id,
            CuratorOperatorCredential.role == role.value,
            CuratorOperatorCredential.active.is_(True),
        )
    )
    if credential is None or not _scope_matches_credential(session, credential, scope):
        raise CuratorAuthError("curator credential scope invalid at consumption")
    return _ConsumedCuratorDecision(
        admin_actor_id=admin.id,
        admin_actor_external_code=admin.external_code,
        role=role,
        operation=operation,
        binding_digest=expected_binding,
        scope=scope,
        jti=jti,
        key_id=key_id,
        issued_at=iat,
    )


def _durable_envelope(
    claim_body: dict[str, Any],
    decision: _ConsumedCuratorDecision,
    *,
    signed_at_iso: str,
) -> dict[str, Any]:
    return {
        "v": DURABLE_APPROVAL_VERSION,
        "kid": decision.key_id,
        "claim": claim_body,
        "admin_actor_id": decision.admin_actor_id,
        "admin_external_code": decision.admin_actor_external_code,
        "role": decision.role.value,
        "operation": decision.operation.value,
        "binding_digest": decision.binding_digest,
        "scope": _scope_dict(decision.scope),
        "jti": decision.jti,
        "signed_at": signed_at_iso,
        "issued_at": decision.issued_at,
    }


def _verify_claim_binding_consistency(
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    claim_body: dict[str, Any],
    claim_id: str,
) -> None:
    if str(claim_id) != str(claim_body.get("claim_id") or ""):
        raise CuratorAuthError("claim_id does not match claim body")
    bound_claim = str(binding_payload.get("claim_id") or "")
    if bound_claim and bound_claim != str(claim_id):
        raise CuratorAuthError("claim_id does not match operation binding")
    if operation == CuratorOperation.MAPPING_APPROVE:
        for key in (
            "revision_id",
            "misconception_code",
            "source_locator",
            "mapping_registry_version",
            "organization_id",
            "institution_id",
            "curriculum_version_id",
        ):
            if str(binding_payload.get(key) or "") != str(claim_body.get(key) or ""):
                raise CuratorAuthError("mapping claim body does not match binding")
        bound_codes = binding_payload.get("candidate_concept_codes")
        body_codes = claim_body.get("candidate_concept_codes")
        if bound_codes is not None and body_codes is not None:
            if sorted(str(c) for c in bound_codes) != sorted(str(c) for c in body_codes):
                raise CuratorAuthError("mapping claim body does not match binding")
        for key in (
            "source_approval_fingerprint",
            "source_snapshot_checksum",
            "source_content_checksum",
            "source_span_checksum",
        ):
            if str(binding_payload.get(key) or "") != str(claim_body.get(key) or ""):
                raise CuratorAuthError("mapping claim body does not match source evidence binding")
            if not str(binding_payload.get(key) or "").strip():
                raise CuratorAuthError("mapping approve binding missing source evidence")
    elif operation == CuratorOperation.MANDATORY_POLICY_APPROVE:
        for key in (
            "policy_rule_id",
            "source_revision_id",
            "scope_type",
            "scope_code",
            "policy_key",
            "value_checksum",
            "rule_lifecycle_digest",
            "source_approval_fingerprint",
            "source_snapshot_checksum",
            "source_content_checksum",
            "mandatory_source_locator",
            "source_span_checksum",
        ):
            if str(binding_payload.get(key) or "") != str(claim_body.get(key) or ""):
                raise CuratorAuthError("mandatory policy claim body does not match binding")
        for key in (
            "source_approval_fingerprint",
            "source_snapshot_checksum",
            "source_content_checksum",
            "mandatory_source_locator",
            "source_span_checksum",
        ):
            if not str(binding_payload.get(key) or "").strip():
                raise CuratorAuthError("mandatory policy approve binding missing source evidence")
    elif operation in _DURABLE_REVOCATION_OPERATIONS:
        if str(binding_payload.get("claim_id") or "") != str(claim_id):
            raise CuratorAuthError("revocation claim_id does not match binding")


def _sign_envelope(envelope: dict[str, Any], signing_key: str) -> str:
    encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        signing_key.encode("utf-8"),
        f"durable-v{DURABLE_APPROVAL_VERSION}:{encoded}".encode(),
        hashlib.sha256,
    ).hexdigest()


def consume_decision_and_build_signed_payload(
    session: Session,
    *,
    token: str,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    scope: CuratorScope,
    claim_body: dict[str, Any],
    claim_id: str,
) -> dict[str, Any]:
    """Atomic consume short-lived decision + sign durable claim envelope."""
    decision = _consume_curator_write_decision(
        session,
        token=token,
        role=role,
        operation=operation,
        binding_payload=binding_payload,
        scope=scope,
    )
    existing = session.scalar(
        select(CuratorDurableApprovalRecord).where(
            CuratorDurableApprovalRecord.decision_jti == decision.jti
        )
    )
    if existing is not None:
        raise CuratorAuthError("curator decision jti already consumed for durable approval")
    _verify_claim_binding_consistency(operation, binding_payload, claim_body, claim_id)
    key_id, signing_key = _require_signing_key()
    signed_at = datetime.now(tz=UTC).isoformat()
    body = dict(claim_body)
    body["approved_by"] = decision.admin_actor_external_code
    envelope = _durable_envelope(body, decision, signed_at_iso=signed_at)
    signature = _sign_envelope(envelope, signing_key)
    session.add(
        CuratorDurableApprovalRecord(
            decision_jti=decision.jti,
            operation=operation.value,
            claim_id=claim_id,
            admin_actor_id=decision.admin_actor_id,
        )
    )
    session.flush()
    return {
        **body,
        "curator_approval": {**envelope, "signature": signature},
    }


def attach_source_audit_event_to_durable_record(
    session: Session, *, decision_jti: str, source_audit_event_id: str
) -> None:
    record = session.scalar(
        select(CuratorDurableApprovalRecord).where(
            CuratorDurableApprovalRecord.decision_jti == decision_jti
        )
    )
    if record is not None:
        record.source_audit_event_id = source_audit_event_id
        session.flush()


def mark_durable_approval_revoked(session: Session, *, claim_id: str) -> None:
    records = session.scalars(
        select(CuratorDurableApprovalRecord).where(
            CuratorDurableApprovalRecord.claim_id == claim_id,
            CuratorDurableApprovalRecord.revoked_at_iso.is_(None),
            CuratorDurableApprovalRecord.operation.in_(_DURABLE_APPROVAL_OPERATIONS),
        )
    ).all()
    revoked_at = datetime.now(tz=UTC).isoformat()
    for record in records:
        record.revoked_at_iso = revoked_at
        session.flush()


def verify_durable_curator_approval(
    session: Session,
    payload: dict[str, Any],
    *,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    audit_actor_id: str | None = None,
    expected_scope: CuratorScope | None = None,
    source_audit_event_id: str | None = None,
) -> bool:
    approval = payload.get("curator_approval")
    if not isinstance(approval, dict):
        return False
    if int(approval.get("v") or 0) != DURABLE_APPROVAL_VERSION:
        return False
    if str(approval.get("role") or "") != role.value:
        return False
    if str(approval.get("operation") or "") != operation.value:
        return False
    expected_binding = operation_binding_digest(operation.value, binding_payload)
    if str(approval.get("binding_digest") or "") != expected_binding:
        return False
    admin_id = str(approval.get("admin_actor_id") or "").strip()
    admin_code = str(approval.get("admin_external_code") or "").strip()
    approved_by = str(payload.get("approved_by") or "").strip()
    if not admin_id or not admin_code:
        return False
    if approved_by and approved_by not in {admin_code, admin_id}:
        return False
    if source_audit_event_id:
        if not str(audit_actor_id or "").strip():
            return False
        if str(audit_actor_id).strip() not in {admin_code, admin_id}:
            return False
        from app.models.source import SourceAuditEvent

        audit_event = session.get(SourceAuditEvent, source_audit_event_id)
        if audit_event is None:
            return False
        persisted_actor = str(audit_event.actor_id or "").strip()
        if not persisted_actor:
            return False
        if persisted_actor not in {admin_code, admin_id}:
            return False
    elif audit_actor_id and str(audit_actor_id).strip() not in {admin_code, admin_id}:
        return False
    admin = session.get(AdminActor, admin_id)
    if admin is None or not admin.active or admin.external_code != admin_code:
        return False
    scope_payload_pre = approval.get("scope") or {}
    if isinstance(scope_payload_pre, dict):
        if scope_payload_pre.get("organization_id") and (
            not admin.organization_id
            or str(admin.organization_id) != str(scope_payload_pre.get("organization_id"))
        ):
            return False
        if scope_payload_pre.get("institution_id") and (
            not admin.institution_id
            or str(admin.institution_id) != str(scope_payload_pre.get("institution_id"))
        ):
            return False
    scope_payload = approval.get("scope") or {}
    if not isinstance(scope_payload, dict):
        return False
    try:
        approval_scope = CuratorScope(
            organization_id=str(scope_payload.get("organization_id") or ""),
            institution_id=str(scope_payload.get("institution_id") or ""),
            curriculum_version_id=str(scope_payload.get("curriculum_version_id") or "") or None,
            teacher_id=str(scope_payload.get("teacher_id") or "") or None,
            board_code=str(scope_payload.get("board_code") or "") or None,
        )
    except (TypeError, ValueError):
        return False
    try:
        _assert_tenant_scope_active(session, approval_scope)
    except CuratorAuthError:
        return False
    credential = None
    for candidate in session.scalars(
        select(CuratorOperatorCredential).where(
            CuratorOperatorCredential.admin_actor_id == admin.id,
            CuratorOperatorCredential.role == role.value,
            CuratorOperatorCredential.active.is_(True),
        )
    ).all():
        if _scope_matches_credential(session, candidate, approval_scope):
            credential = candidate
            break
    if credential is None:
        return False
    if expected_scope is not None:
        for field in (
            "organization_id",
            "institution_id",
            "curriculum_version_id",
            "teacher_id",
            "board_code",
        ):
            exp = getattr(expected_scope, field)
            if exp is None:
                continue
            if field != "organization_id" and not str(exp).strip():
                continue
            got = getattr(approval_scope, field)
            if str(exp) != str(got or ""):
                return False
    jti = str(approval.get("jti") or "").strip()
    if not jti:
        return False
    lineage = session.scalar(
        select(CuratorDurableApprovalRecord).where(
            CuratorDurableApprovalRecord.decision_jti == jti
        )
    )
    if lineage is None:
        return False
    if str(lineage.operation) != operation.value:
        return False
    if operation.value in _DURABLE_APPROVAL_OPERATIONS and lineage.revoked_at_iso is not None:
        return False
    if str(lineage.admin_actor_id) != admin_id:
        return False
    if str(lineage.claim_id) != str(payload.get("claim_id") or ""):
        return False
    if not source_audit_event_id or not lineage.source_audit_event_id:
        return False
    if str(lineage.source_audit_event_id) != str(source_audit_event_id):
        return False
    try:
        key_id, signing_key = _require_signing_key()
    except CuratorAuthError:
        return False
    if str(approval.get("kid") or "") != key_id:
        return False
    envelope = {key: approval[key] for key in approval if key != "signature"}
    expected_sig = _sign_envelope(envelope, signing_key)
    supplied = str(approval.get("signature") or "")
    if not hmac.compare_digest(expected_sig, supplied):
        return False
    claim_in_envelope = approval.get("claim")
    if not isinstance(claim_in_envelope, dict):
        return False
    body_without_approval = {k: v for k, v in payload.items() if k != "curator_approval"}
    if body_without_approval != claim_in_envelope:
        return False
    return True


# Backward-compatible alias for tests migrating to consume_decision_and_build_signed_payload
def verify_and_consume_curator_write_decision(
    session: Session,
    *,
    token: str,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    scope: CuratorScope,
) -> _ConsumedCuratorDecision:
    return _consume_curator_write_decision(
        session,
        token=token,
        role=role,
        operation=operation,
        binding_payload=binding_payload,
        scope=scope,
    )
