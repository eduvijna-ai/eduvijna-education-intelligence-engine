from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import policy_rule_sources
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source import Source


class PolicyRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_rules"

    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_code: Mapped[str] = mapped_column(String(128), index=True)
    policy_key: Mapped[str] = mapped_column(String(255), index=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    sources: Mapped[list[Source]] = relationship(secondary=policy_rule_sources)
