"""close Day 1 and Day 2 audit gaps

Revision ID: 20261001_0003
Revises: 20261001_0002
Create Date: 2026-10-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261001_0003"
down_revision = "20261001_0002"
branch_labels = None
depends_on = None


def _id() -> sa.Column[str]:
    return sa.Column("id", sa.String(length=36), primary_key=True, nullable=False)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "organizations",
        _id(),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_organization_code"),
    )
    op.create_index("ix_organizations_code", "organizations", ["code"], unique=True)

    op.create_table(
        "institutions",
        _id(),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "code", name="uq_institution_org_code"),
    )
    op.create_index("ix_institutions_organization_id", "institutions", ["organization_id"])

    op.create_table(
        "teachers",
        _id(),
        sa.Column(
            "institution_id",
            sa.String(36),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_code", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("institution_id", "external_code", name="uq_teacher_institution_code"),
    )
    op.create_index("ix_teachers_institution_id", "teachers", ["institution_id"])

    op.create_table(
        "learners",
        _id(),
        sa.Column(
            "institution_id",
            sa.String(36),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_teacher_id",
            sa.String(36),
            sa.ForeignKey("teachers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_code", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("institution_id", "external_code", name="uq_learner_institution_code"),
    )
    op.create_index("ix_learners_institution_id", "learners", ["institution_id"])
    op.create_index("ix_learners_primary_teacher_id", "learners", ["primary_teacher_id"])

    op.create_table(
        "admin_actors",
        _id(),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "institution_id",
            sa.String(36),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("external_code", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("external_code", name="uq_admin_actor_external_code"),
    )
    op.create_index("ix_admin_actors_organization_id", "admin_actors", ["organization_id"])
    op.create_index("ix_admin_actors_institution_id", "admin_actors", ["institution_id"])
    op.create_index("ix_admin_actors_external_code", "admin_actors", ["external_code"], unique=True)

    op.create_table(
        "api_clients",
        _id(),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.String(36),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("client_code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("client_code", name="uq_api_client_code"),
    )
    op.create_index("ix_api_clients_organization_id", "api_clients", ["organization_id"])
    op.create_index("ix_api_clients_institution_id", "api_clients", ["institution_id"])
    op.create_index("ix_api_clients_client_code", "api_clients", ["client_code"], unique=True)

    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("age_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("age_max", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "grade_year_codes",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch.add_column(
            sa.Column(
                "rubric_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.create_check_constraint("ck_question_age_min", "age_min IS NULL OR age_min >= 0")
        batch.create_check_constraint("ck_question_age_max", "age_max IS NULL OR age_max >= 0")
        batch.create_check_constraint(
            "ck_question_age_range",
            "age_min IS NULL OR age_max IS NULL OR age_min <= age_max",
        )


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_constraint("ck_question_age_range", type_="check")
        batch.drop_constraint("ck_question_age_max", type_="check")
        batch.drop_constraint("ck_question_age_min", type_="check")
        batch.drop_column("rubric_json")
        batch.drop_column("grade_year_codes")
        batch.drop_column("age_max")
        batch.drop_column("age_min")

    op.drop_index("ix_api_clients_client_code", table_name="api_clients")
    op.drop_index("ix_api_clients_institution_id", table_name="api_clients")
    op.drop_index("ix_api_clients_organization_id", table_name="api_clients")
    op.drop_table("api_clients")

    op.drop_index("ix_admin_actors_external_code", table_name="admin_actors")
    op.drop_index("ix_admin_actors_institution_id", table_name="admin_actors")
    op.drop_index("ix_admin_actors_organization_id", table_name="admin_actors")
    op.drop_table("admin_actors")

    op.drop_index("ix_learners_primary_teacher_id", table_name="learners")
    op.drop_index("ix_learners_institution_id", table_name="learners")
    op.drop_table("learners")

    op.drop_index("ix_teachers_institution_id", table_name="teachers")
    op.drop_table("teachers")

    op.drop_index("ix_institutions_organization_id", table_name="institutions")
    op.drop_table("institutions")

    op.drop_index("ix_organizations_code", table_name="organizations")
    op.drop_table("organizations")
