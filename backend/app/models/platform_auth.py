from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationPrincipal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_principals"
    __table_args__ = (
        UniqueConstraint("organization_id", "login_code", name="uq_principal_org_login"),
        CheckConstraint(
            "(CASE WHEN teacher_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN learner_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_actor_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_principal_exactly_one_actor",
        ),
        ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_principal_institution_org",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    learner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    admin_actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_actors.id", ondelete="CASCADE"), index=True
    )
    login_code: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ApplicationRefreshSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_refresh_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_token_hash"),)

    principal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("application_principals.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_epoch: Mapped[int] = mapped_column(default=0, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("application_refresh_sessions.id", ondelete="SET NULL")
    )


class ApplicationApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_api_keys"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_api_key_prefix"),
        ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_api_key_institution_org",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    created_by_principal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("application_principals.id", ondelete="SET NULL")
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    secret_hash_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SecurityAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_audit_events"

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    principal_id: Mapped[str | None] = mapped_column(String(36), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
