from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CuratorOperatorCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Hashed internal operator secret bound to an AdminActor and scoped curator role."""

    __tablename__ = "curator_operator_credentials"
    __table_args__ = (
        UniqueConstraint(
            "admin_actor_id",
            "role",
            name="uq_curator_credential_actor_role",
        ),
    )

    admin_actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_actors.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), index=True)
    curriculum_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    board_code: Mapped[str | None] = mapped_column(String(64), index=True)
    board_scope_authorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credential_hash_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CuratorBootstrapAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curator_bootstrap_audit_events"

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    admin_actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CuratorDurableApprovalRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curator_durable_approval_records"
    __table_args__ = (UniqueConstraint("decision_jti", name="uq_curator_durable_decision_jti"),)

    decision_jti: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    admin_actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_audit_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoked_at_iso: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CuratorDecisionNonce(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Prevents replay of consumed short-lived curator write decisions."""

    __tablename__ = "curator_decision_nonces"
    __table_args__ = (UniqueConstraint("jti", name="uq_curator_decision_jti"),)

    jti: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at_iso: Mapped[str] = mapped_column(String(64), nullable=False)
