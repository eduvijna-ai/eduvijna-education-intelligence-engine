"""Day17 application auth, API keys, audit, and durable async jobs

Revision ID: 20261124_0022
Revises: 20261124_0021
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261124_0022"
down_revision = "20261124_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_principals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("teacher_id", sa.String(length=36), nullable=True),
        sa.Column("learner_id", sa.String(length=36), nullable=True),
        sa.Column("admin_actor_id", sa.String(length=36), nullable=True),
        sa.Column("login_code", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("password_hash_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["admin_actor_id"], ["admin_actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_principal_institution_org",
        ),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(CASE WHEN teacher_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN learner_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_actor_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_principal_exactly_one_actor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "login_code", name="uq_principal_org_login"),
    )
    op.create_index("ix_application_principals_organization_id", "application_principals", ["organization_id"])
    op.create_index("ix_application_principals_institution_id", "application_principals", ["institution_id"])

    op.create_table(
        "application_refresh_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["application_principals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["application_refresh_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )
    op.create_index("ix_application_refresh_sessions_principal_id", "application_refresh_sessions", ["principal_id"])
    op.create_index("ix_application_refresh_sessions_family_id", "application_refresh_sessions", ["family_id"])

    op.create_table(
        "application_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_principal_id", sa.String(length=36), nullable=True),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("secret_hash_json", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_principal_id"], ["application_principals.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_api_key_institution_org",
        ),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_prefix", name="uq_api_key_prefix"),
    )
    op.create_index("ix_application_api_keys_organization_id", "application_api_keys", ["organization_id"])

    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("principal_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_events_event_type", "security_audit_events", ["event_type"])
    op.create_index("ix_security_audit_events_correlation_id", "security_audit_events", ["correlation_id"])

    op.create_table(
        "durable_async_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("principal_id", sa.String(length=36), nullable=True),
        sa.Column("api_key_id", sa.String(length=36), nullable=True),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column("actor_ref", sa.String(length=128), nullable=False),
        sa.Column("capability_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_holder", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_fence", sa.Integer(), nullable=False),
        sa.Column("synthetic_fixture_only", sa.Boolean(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["application_api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_job_institution_org",
        ),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["application_principals.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_job_org_idempotency"
        ),
    )
    op.create_index("ix_durable_async_jobs_capability_code", "durable_async_jobs", ["capability_code"])
    op.create_index("ix_durable_async_jobs_status", "durable_async_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("durable_async_jobs")
    op.drop_table("security_audit_events")
    op.drop_table("application_api_keys")
    op.drop_table("application_refresh_sessions")
    op.drop_table("application_principals")