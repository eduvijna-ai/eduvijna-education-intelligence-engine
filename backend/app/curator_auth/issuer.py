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
from app.models.curator_auth import CuratorDecisionNonce, CuratorOperatorCredential
from app.models.tenancy import AdminActor
from app.prerequisite_intelligence.stable_ids import stable_audit_ref

UNSAFE_CURATOR_SIGNING_KEYS = frozenset(
    {
        "",
        "local-development-only",
        "change-me-for-non-local-use",
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
class VerifiedCuratorDecision:
    admin_actor_id: str
    admin_actor_external_code: str
    role: CuratorRole
    operation: CuratorOperation
    binding_digest: str
    scope: CuratorScope
    jti: str
    key_id: str


def _require_signing_key() -> tuple[str, str]:
    settings = get_settings()
    key = (settings.curator_approval_signing_key or "").strip()
    key_id = (settings.curator_approval_signing_key_id or "curator-approval-v1").strip()
    if not key or key in UNSAFE_CURATOR_SIGNING_KEYS:
        raise CuratorAuthError("curator approval signing key is not configured")
    if key == settings.api_secret_key:
        raise CuratorAuthError("curator approval signing key must not equal API secret")
    return key_id, key


def operation_binding_digest(operation: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"operation": operation, **payload},
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


def provision_operator_credential(
    session: Session,
    *,
    admin_actor: AdminActor,
    role: CuratorRole,
    operator_secret: str,
    scope: CuratorScope,
) -> CuratorOperatorCredential:
    if not operator_secret or len(operator_secret) < 16:
        raise CuratorAuthError("operator secret must be at least 16 characters")
    existing = session.scalar(
        select(CuratorOperatorCredential).where(
            CuratorOperatorCredential.admin_actor_id == admin_actor.id,
            CuratorOperatorCredential.role == role.value,
        )
    )
    record = existing or CuratorOperatorCredential(
        admin_actor_id=admin_actor.id,
        role=role.value,
    )
    record.organization_id = scope.organization_id or None
    record.institution_id = scope.institution_id or None
    record.teacher_id = scope.teacher_id
    record.credential_hash_json = hash_operator_secret(operator_secret)
    record.active = True
    session.add(record)
    session.flush()
    return record


def _scope_matches_credential(
    credential: CuratorOperatorCredential, scope: CuratorScope
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
        if not scope.teacher_id or str(credential.teacher_id) != str(scope.teacher_id):
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
    if not _scope_matches_credential(credential, scope):
        raise CuratorAuthError("curator credential scope mismatch")
    if not verify_operator_secret(operator_secret, credential.credential_hash_json):
        raise CuratorAuthError("curator operator credential verification failed")
    return admin


def _encode_token(payload: dict[str, Any], signing_key: str) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
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
    exp = now + timedelta(seconds=ttl_seconds)
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
        "scope": {
            "organization_id": scope.organization_id,
            "institution_id": scope.institution_id,
            "curriculum_version_id": scope.curriculum_version_id,
            "teacher_id": scope.teacher_id,
            "board_code": scope.board_code,
        },
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


def verify_and_consume_curator_write_decision(
    session: Session,
    *,
    token: str,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
    scope: CuratorScope,
) -> VerifiedCuratorDecision:
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
    if scope.curriculum_version_id is not None:
        if str(scope_payload.get("curriculum_version_id") or "") != str(
            scope.curriculum_version_id
        ):
            raise CuratorAuthError("curator decision curriculum scope mismatch")
    if scope.teacher_id is not None:
        if str(scope_payload.get("teacher_id") or "") != str(scope.teacher_id):
            raise CuratorAuthError("curator decision teacher scope mismatch")
    if scope.board_code is not None:
        if str(scope_payload.get("board_code") or "") != str(scope.board_code):
            raise CuratorAuthError("curator decision board scope mismatch")
    exp = int(payload.get("exp") or 0)
    if datetime.now(tz=UTC).timestamp() > exp:
        raise CuratorAuthError("curator decision token expired")
    jti = str(payload.get("jti") or "").strip()
    if not jti:
        raise CuratorAuthError("curator decision token missing jti")
    nonce = session.scalar(
        select(CuratorDecisionNonce).where(CuratorDecisionNonce.jti == jti)
    )
    if nonce is None:
        raise CuratorAuthError("curator decision jti is unknown")
    session.delete(nonce)
    session.flush()
    admin_id = str(payload.get("admin_actor_id") or "").strip()
    admin = session.get(AdminActor, admin_id)
    if admin is None or not admin.active:
        raise CuratorAuthError("curator decision admin actor is not active")
    return VerifiedCuratorDecision(
        admin_actor_id=admin.id,
        admin_actor_external_code=admin.external_code,
        role=role,
        operation=operation,
        binding_digest=expected_binding,
        scope=scope,
        jti=jti,
        key_id=key_id,
    )


def sign_durable_curator_approval(
    claim_body: dict[str, Any],
    *,
    decision: VerifiedCuratorDecision,
) -> dict[str, Any]:
    key_id, signing_key = _require_signing_key()
    encoded = json.dumps(claim_body, sort_keys=True, separators=(",", ":"))
    digest_input = f"durable-v1:{key_id}:{encoded}"
    signature = hmac.new(
        signing_key.encode("utf-8"),
        digest_input.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        **claim_body,
        "curator_approval": {
            "v": 1,
            "kid": key_id,
            "admin_actor_id": decision.admin_actor_id,
            "admin_external_code": decision.admin_actor_external_code,
            "role": decision.role.value,
            "operation": decision.operation.value,
            "binding_digest": decision.binding_digest,
            "jti": decision.jti,
            "signature": signature,
        },
    }


def verify_durable_curator_approval(
    session: Session,
    payload: dict[str, Any],
    *,
    role: CuratorRole,
    operation: CuratorOperation,
    binding_payload: dict[str, Any],
) -> bool:
    approval = payload.get("curator_approval")
    if not isinstance(approval, dict):
        return False
    if int(approval.get("v") or 0) != 1:
        return False
    if str(approval.get("role") or "") != role.value:
        return False
    if str(approval.get("operation") or "") != operation.value:
        return False
    expected_binding = operation_binding_digest(operation.value, binding_payload)
    if str(approval.get("binding_digest") or "") != expected_binding:
        return False
    admin_id = str(approval.get("admin_actor_id") or "").strip()
    admin = session.get(AdminActor, admin_id)
    if admin is None or not admin.active:
        return False
    credential = session.scalar(
        select(CuratorOperatorCredential).where(
            CuratorOperatorCredential.admin_actor_id == admin.id,
            CuratorOperatorCredential.role == role.value,
            CuratorOperatorCredential.active.is_(True),
        )
    )
    if credential is None:
        return False
    try:
        key_id, signing_key = _require_signing_key()
    except CuratorAuthError:
        return False
    if str(approval.get("kid") or "") != key_id:
        return False
    body = {key: value for key, value in payload.items() if key != "curator_approval"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    digest_input = f"durable-v1:{key_id}:{encoded}"
    expected_sig = hmac.new(
        signing_key.encode("utf-8"),
        digest_input.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    supplied = str(approval.get("signature") or "")
    if not hmac.compare_digest(expected_sig, supplied):
        return False
    return True
