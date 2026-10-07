"""Day 6 education intelligence validator persistence

Revision ID: 20261007_0010
Revises: 20261004_0009
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261007_0010"
down_revision = "20261004_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ei_taxonomy_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registry_key", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ei_taxonomy_registry_registry_key", "ei_taxonomy_registry", ["registry_key"])
    op.create_index("ix_ei_taxonomy_registry_version", "ei_taxonomy_registry", ["version"])
    op.create_index("ix_ei_taxonomy_registry_status", "ei_taxonomy_registry", ["status"])

    op.create_table(
        "ei_policy_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registry_key", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ei_policy_registry_registry_key", "ei_policy_registry", ["registry_key"])
    op.create_index("ix_ei_policy_registry_version", "ei_policy_registry", ["version"])
    op.create_index("ix_ei_policy_registry_status", "ei_policy_registry", ["status"])

    op.create_table(
        "ei_validation_audit_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("aggregate_status", sa.String(32), nullable=False),
        sa.Column("blocking_failure", sa.Boolean(), nullable=False),
        sa.Column("institution_id", sa.String(36), nullable=True),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ei_validation_audit_runs_run_id", "ei_validation_audit_runs", ["run_id"], unique=True)
    op.create_index(
        "ix_ei_validation_audit_runs_input_hash", "ei_validation_audit_runs", ["input_hash"]
    )
    op.create_index(
        "ix_ei_validation_audit_runs_institution_id", "ei_validation_audit_runs", ["institution_id"]
    )
    op.create_index("ix_ei_validation_audit_runs_actor_id", "ei_validation_audit_runs", ["actor_id"])

    op.create_table(
        "ei_quality_rule_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pack_key", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_ei_quality_rule_packs_pack_key", "ei_quality_rule_packs", ["pack_key"])
    op.create_index("ix_ei_quality_rule_packs_version", "ei_quality_rule_packs", ["version"])
    op.create_index("ix_ei_quality_rule_packs_status", "ei_quality_rule_packs", ["status"])


def downgrade() -> None:
    op.drop_table("ei_quality_rule_packs")
    op.drop_table("ei_validation_audit_runs")
    op.drop_table("ei_policy_registry")
    op.drop_table("ei_taxonomy_registry")
