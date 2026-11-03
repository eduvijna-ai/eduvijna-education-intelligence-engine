"""Privileged offline curator credential provisioning (not for runtime business callers)."""

from __future__ import annotations

import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.curator_auth.issuer import (
    CuratorAuthError,
    CuratorScope,
    hash_operator_secret,
)
from app.curator_auth.roles import CuratorRole
from app.models.curator_auth import CuratorBootstrapAuditEvent, CuratorOperatorCredential
from app.models.tenancy import AdminActor

MIN_BOOTSTRAP_SECRET_LEN = 32
MIN_OPERATOR_SECRET_LEN = 16


def _verify_bootstrap_secret(provided: str) -> None:
    settings = get_settings()
    expected = (settings.curator_bootstrap_secret or "").strip()
    if not expected or len(expected) < MIN_BOOTSTRAP_SECRET_LEN:
        raise CuratorAuthError("curator bootstrap secret is not configured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise CuratorAuthError("curator bootstrap authorization failed")


def provision_operator_credential(
    session: Session,
    *,
    bootstrap_secret: str,
    admin_actor: AdminActor,
    role: CuratorRole,
    operator_secret: str,
    scope: CuratorScope,
    board_scope_authorized: bool = False,
) -> CuratorOperatorCredential:
    """Create or rotate a curator operator credential. Requires bootstrap secret."""
    _verify_bootstrap_secret(bootstrap_secret)
    if len(operator_secret) < MIN_OPERATOR_SECRET_LEN:
        raise CuratorAuthError("operator secret must be at least 16 characters")
    if board_scope_authorized and not scope.board_code:
        raise CuratorAuthError("board_scope_authorized requires board_code on grant")
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
    if scope.teacher_id is not None:
        record.teacher_id = scope.teacher_id
    if scope.curriculum_version_id is not None:
        record.curriculum_version_id = scope.curriculum_version_id
    if board_scope_authorized:
        record.board_scope_authorized = True
        record.board_code = scope.board_code
    elif existing is None:
        record.board_scope_authorized = False
        record.board_code = scope.board_code
    record.credential_hash_json = hash_operator_secret(operator_secret)
    record.active = True
    session.add(record)
    session.add(
        CuratorBootstrapAuditEvent(
            action="credential_provisioned",
            admin_actor_id=admin_actor.id,
            role=role.value,
            payload_json={
                "organization_id": scope.organization_id,
                "institution_id": scope.institution_id,
                "curriculum_version_id": scope.curriculum_version_id,
                "teacher_id": scope.teacher_id,
                "board_code": scope.board_code,
                "board_scope_authorized": bool(board_scope_authorized),
            },
        )
    )
    session.flush()
    return record


def generate_test_bootstrap_secret() -> str:
    return secrets.token_hex(32)
