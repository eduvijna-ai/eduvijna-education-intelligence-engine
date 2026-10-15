from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OrchestrationAuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_audit_events"

    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_revision_ids_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    issue_codes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    gateway_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class OrchestrationIdempotencyRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_idempotency"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_orchestration_idempotency_key"),)

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestrationCheckpointLease(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_checkpoint_leases"

    thread_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
