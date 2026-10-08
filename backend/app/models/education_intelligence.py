from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TaxonomyRegistryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ei_taxonomy_registry"

    registry_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PolicyRegistryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ei_policy_registry"

    registry_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ValidationAuditRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ei_validation_audit_runs"

    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_status: Mapped[str] = mapped_column(String(32), nullable=False)
    blocking_failure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    institution_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class EducationalQualityRulePack(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ei_quality_rule_packs"

    pack_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    rules_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
