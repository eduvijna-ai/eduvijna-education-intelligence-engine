from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeSourceBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ki_source_bindings"
    __table_args__ = (
        UniqueConstraint(
            "source_revision_id",
            "retrieval_profile_version",
            name="uq_ki_binding_revision_profile",
        ),
        Index("ix_ki_binding_source_active", "source_id", "index_status"),
        CheckConstraint(
            "(index_status = 'active' AND retired_at IS NULL) OR (index_status <> 'active')",
            name="ck_ki_binding_active_not_retired",
        ),
    )

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    source_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_revisions.id", ondelete="CASCADE"), index=True
    )
    source_revision_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    anythingllm_workspace: Mapped[str] = mapped_column(String(255), nullable=False)
    anythingllm_document_id: Mapped[str | None] = mapped_column(String(255))
    ownership_scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), index=True)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieval_profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ki_audit_events"

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_id: Mapped[str | None] = mapped_column(String(64), index=True)
    query_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), index=True)
    retrieval_profile_version: Mapped[str | None] = mapped_column(String(64), index=True)
    workspaces_queried_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_revision_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    warnings_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
