from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

D13_REPLAY_RESERVATION_TABLE = "d13_replay_reservations"
D13_SYNTHETIC_TEST_ONLY_KEY = "d13_synthetic_test_only"


class D13ReplayReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """D13-31A durable SQL idempotency envelope — not paper issuance."""

    __tablename__ = D13_REPLAY_RESERVATION_TABLE
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "institution_id",
            "exam_pack_code",
            "exam_version_id",
            "academic_year",
            "idempotency_key_hash",
            name="uq_d13_replay_reservation_scope_key",
        ),
        CheckConstraint("length(request_fingerprint) = 64", name="ck_d13_replay_fp_sha256"),
        CheckConstraint("length(idempotency_key_hash) = 64", name="ck_d13_replay_key_hash_sha256"),
        CheckConstraint(
            "reservation_state in ('reserved', 'in_progress', 'replayed')",
            name="ck_d13_replay_state_valid",
        ),
        CheckConstraint(
            "reservation_state not in ('reserved', 'in_progress') "
            "OR (result_json IS NULL AND payload_sha256 IS NULL "
            "AND result_snapshot_version IS NULL)",
            name="ck_d13_replay_pending_no_payload",
        ),
        CheckConstraint(
            "reservation_state != 'replayed' "
            "OR (owner_token IS NULL AND payload_sha256 IS NOT NULL "
            "AND result_json IS NOT NULL AND result_snapshot_version IS NOT NULL)",
            name="ck_d13_replay_replayed_requires_payload",
        ),
        CheckConstraint("synthetic_test_only = 1", name="ck_d13_replay_synthetic_marker"),
    )

    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    institution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exam_pack_code: Mapped[str] = mapped_column(String(64), nullable=False)
    exam_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reservation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_snapshot_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    synthetic_test_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)