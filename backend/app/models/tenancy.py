from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("code", name="uq_organization_code"),
    )

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Institution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_institution_org_code"),
        UniqueConstraint("id", "organization_id", name="uq_institution_id_org"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Teacher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("institution_id", "external_code", name="uq_teacher_institution_code"),
        UniqueConstraint("id", "institution_id", name="uq_teacher_id_institution"),
    )

    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    external_code: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Learner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learners"
    __table_args__ = (
        UniqueConstraint("institution_id", "external_code", name="uq_learner_institution_code"),
        ForeignKeyConstraint(
            ["primary_teacher_id", "institution_id"],
            ["teachers.id", "teachers.institution_id"],
            name="fk_learner_teacher_same_institution",
        ),
    )

    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    primary_teacher_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    external_code: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AdminActor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_actors"
    __table_args__ = (
        UniqueConstraint("external_code", name="uq_admin_actor_external_code"),
        CheckConstraint(
            "institution_id IS NULL OR organization_id IS NOT NULL",
            name="ck_admin_institution_requires_organization",
        ),
        ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_admin_institution_same_organization",
        ),
    )

    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    external_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ApiClient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_clients"
    __table_args__ = (
        UniqueConstraint("client_code", name="uq_api_client_code"),
        ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_api_client_institution_same_organization",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    client_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
