from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String, UniqueConstraint
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