from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DiagnosticTaxonomyEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_taxonomy_entries"

    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("diagnostic_taxonomy_entries.id", ondelete="SET NULL"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    parent: Mapped[DiagnosticTaxonomyEntry | None] = relationship(
        remote_side="DiagnosticTaxonomyEntry.id",
        back_populates="children",
    )
    children: Mapped[list[DiagnosticTaxonomyEntry]] = relationship(back_populates="parent")
