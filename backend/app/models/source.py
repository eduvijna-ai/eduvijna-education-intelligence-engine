from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import SourceStatus, SourceTrustTier, SourceType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(128), index=True)
    board_or_exam: Mapped[str | None] = mapped_column(String(255), index=True)
    academic_year: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    copyright_classification: Mapped[str | None] = mapped_column(String(128))
    trust_tier: Mapped[str] = mapped_column(
        String(64),
        default=SourceTrustTier.ANALYTICAL.value,
        nullable=False,
    )
    anythingllm_workspace: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(32),
        default=SourceStatus.STAGED.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    @staticmethod
    def official_type_values() -> tuple[str, ...]:
        return (
            SourceType.OFFICIAL_AUTHORITY.value,
            SourceType.OFFICIAL_SYLLABUS.value,
            SourceType.OFFICIAL_EXAM_BULLETIN.value,
            SourceType.OFFICIAL_PAPER.value,
            SourceType.ANSWER_KEY.value,
            SourceType.MARKING_SCHEME.value,
            SourceType.SAMPLE_PAPER.value,
        )
