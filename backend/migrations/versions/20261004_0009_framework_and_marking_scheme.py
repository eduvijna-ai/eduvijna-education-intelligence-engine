"""Add framework structure and exact marking-scheme evidence provenance.

Revision ID: 20261004_0009
Revises: 20261004_0008
Create Date: 2026-10-04
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20261004_0009"
down_revision = "20261004_0008"
branch_labels = None
depends_on = None

_FRAMEWORK_TABLES = ("framework_structure_nodes", "learning_outcome_competency_links")
_OLD_BINDING = (
    "curriculum_version_id",
    "source_revision_id",
    "grade_node_id",
    "subject_node_id",
    "evidence_type",
    "source_locator",
)
_NEW_BINDING = (*_OLD_BINDING[:2], "marking_scheme_revision_id", *_OLD_BINDING[2:])
_MS_FK = "fk_assessment_evidence_marking_scheme_revision"
_MS_INDEX = "ix_assessment_evidence_marking_scheme_revision_id"


def _type_signature(value: sa.types.TypeEngine[Any], bind: sa.Connection) -> str:
    return str(value.compile(dialect=bind.dialect)).upper()


def _normalized_sql(value: str) -> str:
    # Preserve quoted literals exactly; normalizing their case/whitespace could
    # falsely accept a constraint with different allowed values.
    return re.sub(
        r"'(?:(?:'')|[^'])*'|\"(?:(?:\"\")|[^\"])*\"|\s+",
        lambda match: match.group() if match.group()[0] in "'\"" else "",
        value,
    )


def _check_signatures(bind: sa.Connection, table: sa.Table) -> dict[str | None, str]:
    # Reflect a temporary check-only table so each database normalizes the
    # expected SQL just as it normalized the previously issued constraints.
    probe = sa.Table(
        "_eduvijna_0009_" + uuid4().hex,
        sa.MetaData(),
        *(
            sa.Column(column.name, column.type, nullable=column.nullable)
            for column in table.columns
        ),
        *(
            sa.CheckConstraint(str(check.sqltext), name=check.name)
            for check in table.constraints
            if isinstance(check, sa.CheckConstraint)
        ),
        prefixes=["TEMPORARY"],
    )
    probe.create(bind)
    try:
        return {
            item["name"]: _normalized_sql(item["sqltext"])
            for item in sa.inspect(bind).get_check_constraints(probe.name)
        }
    finally:
        probe.drop(bind)


def _validate_existing_framework(bind: sa.Connection, expected: sa.MetaData) -> bool:
    inspector = sa.inspect(bind)
    present = set(inspector.get_table_names()).intersection(_FRAMEWORK_TABLES)
    if not present:
        return False
    if present != set(_FRAMEWORK_TABLES):
        raise RuntimeError("0009 cannot adopt a partial framework schema")
    for name in _FRAMEWORK_TABLES:
        table = expected.tables[name]
        actual_columns = {
            column["name"]: (
                _type_signature(column["type"], bind),
                column["nullable"],
                column.get("default"),
            )
            for column in inspector.get_columns(name)
        }
        expected_columns = {
            column.name: (_type_signature(column.type, bind), column.nullable, None)
            for column in table.columns
        }
        actual_pk = tuple(inspector.get_pk_constraint(name)["constrained_columns"])
        expected_pk = tuple(column.name for column in table.primary_key.columns)
        actual_unique = {
            item["name"]: tuple(item["column_names"])
            for item in inspector.get_unique_constraints(name)
        }
        expected_unique = {
            item.name: tuple(column.name for column in item.columns)
            for item in table.constraints
            if isinstance(item, sa.UniqueConstraint)
        }
        actual_fk = {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                tuple(item["referred_columns"]),
                tuple(
                    item.get("options", {}).get(key)
                    for key in ("ondelete", "onupdate", "deferrable", "initially", "match")
                ),
            )
            for item in inspector.get_foreign_keys(name)
        }
        expected_fk = {
            (
                tuple(element.parent.name for element in item.elements),
                item.referred_table.name,
                tuple(element.column.name for element in item.elements),
                (item.ondelete, item.onupdate, item.deferrable, item.initially, item.match),
            )
            for item in table.foreign_key_constraints
        }
        actual_indexes = {
            item["name"]: (tuple(item["column_names"]), bool(item["unique"]))
            for item in inspector.get_indexes(name)
            if not item.get("duplicates_constraint")
        }
        expected_indexes = {
            item.name: (tuple(column.name for column in item.columns), bool(item.unique))
            for item in table.indexes
        }
        actual_checks = {
            item["name"]: _normalized_sql(item["sqltext"])
            for item in inspector.get_check_constraints(name)
        }
        if (
            actual_columns != expected_columns
            or actual_pk != expected_pk
            or actual_unique != expected_unique
            or actual_fk != expected_fk
            or actual_indexes != expected_indexes
            or actual_checks != _check_signatures(bind, table)
        ):
            raise RuntimeError(f"0009 cannot adopt incompatible framework schema: {name}")
    return True


def _marking_scheme_backfill(bind: sa.Connection) -> list[tuple[str, str]]:
    evidence = sa.Table("assessment_evidence", sa.MetaData(), autoload_with=bind)
    revisions = sa.Table("source_revisions", sa.MetaData(), autoload_with=bind)
    known_revisions = {
        row["id"]: row["metadata_json"]
        for row in bind.execute(sa.select(revisions.c.id, revisions.c.metadata_json)).mappings()
    }
    result: list[tuple[str, str]] = []
    for row in bind.execute(sa.select(evidence.c.id, evidence.c.metadata_json)).mappings():
        metadata = row["metadata_json"]
        if not isinstance(metadata, dict):
            raise RuntimeError(f"0009 invalid assessment metadata for {row['id']}")
        reference = metadata.get("marking_scheme_revision_id")
        if reference is None:
            continue
        if not isinstance(reference, str) or reference not in known_revisions:
            raise RuntimeError(f"0009 invalid marking-scheme revision for evidence {row['id']}")
        revision_metadata = known_revisions[reference]
        if not isinstance(revision_metadata, dict):
            raise RuntimeError(f"0009 invalid source metadata for evidence {row['id']}")
        snapshot = revision_metadata.get("source_snapshot", {})
        if not isinstance(snapshot, dict) or snapshot.get("source_type") not in {
            None,
            "marking_scheme",
        }:
            raise RuntimeError(f"0009 non-marking-scheme target for evidence {row['id']}")
        result.append((row["id"], reference))
    return result


def upgrade() -> None:
    bind = op.get_bind()
    expected = _framework_metadata()
    adopted = _validate_existing_framework(bind, expected)
    backfill = _marking_scheme_backfill(bind)
    # Preflight completes before any persistent schema/data changes.
    if not adopted:
        for name in _FRAMEWORK_TABLES:
            expected.tables[name].create(bind)
    with op.batch_alter_table("assessment_evidence") as batch:
        batch.add_column(sa.Column("marking_scheme_revision_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            _MS_FK, "source_revisions", ["marking_scheme_revision_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index(_MS_INDEX, ["marking_scheme_revision_id"], unique=False)
        batch.drop_constraint("uq_assessment_evidence_binding", type_="unique")
        batch.create_unique_constraint("uq_assessment_evidence_binding", list(_NEW_BINDING))
    evidence = sa.table(
        "assessment_evidence", sa.column("id"), sa.column("marking_scheme_revision_id")
    )
    for evidence_id, revision_id in backfill:
        bind.execute(
            evidence.update()
            .where(evidence.c.id == evidence_id)
            .values(marking_scheme_revision_id=revision_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    evidence = sa.Table("assessment_evidence", sa.MetaData(), autoload_with=bind)
    binding_columns = [evidence.c[name] for name in _OLD_BINDING]
    collisions = bind.execute(
        sa.select(*binding_columns)
        .where(sa.and_(*(column.is_not(None) for column in binding_columns)))
        .group_by(*binding_columns)
        .having(sa.func.count() > 1)
    ).first()
    if collisions is not None:
        raise RuntimeError("0009 downgrade would collapse distinct marking-scheme evidence")
    updates: list[tuple[str, dict[str, Any]]] = []
    for row in bind.execute(
        sa.select(evidence.c.id, evidence.c.marking_scheme_revision_id, evidence.c.metadata_json)
    ).mappings():
        reference = row["marking_scheme_revision_id"]
        if reference is None:
            continue
        metadata = row["metadata_json"]
        if not isinstance(metadata, dict) or (
            metadata.get("marking_scheme_revision_id") is not None
            and metadata.get("marking_scheme_revision_id") != reference
        ):
            raise RuntimeError(f"0009 conflicting marking-scheme metadata for evidence {row['id']}")
        updates.append((row["id"], {**metadata, "marking_scheme_revision_id": reference}))
    for evidence_id, metadata in updates:
        bind.execute(
            evidence.update().where(evidence.c.id == evidence_id).values(metadata_json=metadata)
        )
    with op.batch_alter_table("assessment_evidence") as batch:
        batch.drop_constraint("uq_assessment_evidence_binding", type_="unique")
        batch.drop_index(_MS_INDEX)
        batch.drop_constraint(_MS_FK, type_="foreignkey")
        batch.drop_column("marking_scheme_revision_id")
        batch.create_unique_constraint("uq_assessment_evidence_binding", list(_OLD_BINDING))
    for name in reversed(_FRAMEWORK_TABLES):
        op.drop_table(name)


def _framework_metadata() -> sa.MetaData:
    """Frozen schema for creation and validation of the brief pre-0009 deployment."""
    metadata = sa.MetaData()
    for name in (
        "education_frameworks",
        "competencies",
        "source_revisions",
        "curriculum_versions",
        "learning_outcomes",
    ):
        sa.Table(name, metadata, sa.Column("id", sa.String(36), primary_key=True))

    def index(name: str, table: str, columns: list[str], *, unique: bool) -> None:
        sa.Index(name, *(metadata.tables[table].c[column] for column in columns), unique=unique)

    sa.Table(
        "framework_structure_nodes",
        metadata,
        sa.Column("framework_id", sa.String(length=36), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("official_code", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("official_text", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("parent_level", sa.String(length=32), nullable=True),
        sa.Column("competency_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("publication_status", sa.String(length=16), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("inferred", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(level = 'competency' AND competency_id IS NOT NULL) OR "
            "(level <> 'competency' AND competency_id IS NULL)",
            name="ck_framework_structure_competency_leaf",
        ),
        sa.CheckConstraint(
            "level IN ('stage', 'curricular_area', 'goal', 'competency')",
            name="ck_framework_structure_level",
        ),
        sa.CheckConstraint(
            "(level = 'stage' AND parent_id IS NULL AND parent_level IS NULL) OR "
            "(parent_id IS NOT NULL AND parent_level IS NOT NULL AND ("
            "(level = 'curricular_area' AND parent_level = 'stage') OR "
            "(level = 'goal' AND parent_level = 'curricular_area') OR "
            "(level = 'competency' AND parent_level = 'goal')))",
            name="ck_framework_structure_parent_level",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'final')",
            name="ck_framework_structure_publication_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('review_required', 'reviewed')",
            name="ck_framework_structure_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"], ["competencies.id"], name=None, ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"], ["source_revisions.id"], name=None, ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"], ["education_frameworks.id"], name=None, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "framework_id", "parent_level"],
            [
                "framework_structure_nodes.id",
                "framework_structure_nodes.framework_id",
                "framework_structure_nodes.level",
            ],
            name="fk_framework_structure_parent_scope_level",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "code", name="uq_framework_structure_code"),
        sa.UniqueConstraint("competency_id", name="uq_framework_structure_competency"),
        sa.UniqueConstraint(
            "id", "framework_id", "level", name="uq_framework_structure_id_scope_level"
        ),
    )
    index(
        "ix_framework_structure_nodes_competency_id",
        "framework_structure_nodes",
        ["competency_id"],
        unique=False,
    )
    index(
        "ix_framework_structure_nodes_framework_id",
        "framework_structure_nodes",
        ["framework_id"],
        unique=False,
    )
    index(
        "ix_framework_structure_nodes_level", "framework_structure_nodes", ["level"], unique=False
    )
    index(
        "ix_framework_structure_nodes_parent_id",
        "framework_structure_nodes",
        ["parent_id"],
        unique=False,
    )
    index(
        "ix_framework_structure_nodes_publication_status",
        "framework_structure_nodes",
        ["publication_status"],
        unique=False,
    )
    index(
        "ix_framework_structure_nodes_review_status",
        "framework_structure_nodes",
        ["review_status"],
        unique=False,
    )
    index(
        "ix_framework_structure_nodes_source_revision_id",
        "framework_structure_nodes",
        ["source_revision_id"],
        unique=False,
    )
    sa.Table(
        "learning_outcome_competency_links",
        metadata,
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=False),
        sa.Column("learning_outcome_id", sa.String(length=36), nullable=False),
        sa.Column("framework_id", sa.String(length=36), nullable=False),
        sa.Column("competency_node_id", sa.String(length=36), nullable=False),
        sa.Column("competency_node_level", sa.String(length=32), nullable=False),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("inferred", sa.Boolean(), nullable=False),
        sa.Column("publication_status", sa.String(length=16), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status <> 'direct' OR (inferred = false AND review_status = 'reviewed' "
            "AND evidence_text IS NOT NULL)",
            name="ck_lo_competency_direct_evidence",
        ),
        sa.CheckConstraint(
            "status = 'direct' OR inferred = true", name="ck_lo_competency_inferred_status"
        ),
        sa.CheckConstraint("competency_node_level = 'competency'", name="ck_lo_competency_leaf"),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'final')", name="ck_lo_competency_publication_status"
        ),
        sa.CheckConstraint(
            "review_status IN ('review_required', 'reviewed')",
            name="ck_lo_competency_review_status",
        ),
        sa.CheckConstraint(
            "status IN ('direct', 'partial', 'unresolved', 'review_required')",
            name="ck_lo_competency_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"], ["source_revisions.id"], name=None, ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["learning_outcome_id"], ["learning_outcomes.id"], name=None, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"], ["education_frameworks.id"], name=None, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"], ["curriculum_versions.id"], name=None, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competency_node_id", "framework_id", "competency_node_level"],
            [
                "framework_structure_nodes.id",
                "framework_structure_nodes.framework_id",
                "framework_structure_nodes.level",
            ],
            name="fk_lo_competency_framework_leaf",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "learning_outcome_id",
            "competency_node_id",
            "relationship_type",
            "source_revision_id",
            name="uq_learning_outcome_competency_evidence",
        ),
    )
    index(
        "ix_learning_outcome_competency_links_competency_node_id",
        "learning_outcome_competency_links",
        ["competency_node_id"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_curriculum_version_id",
        "learning_outcome_competency_links",
        ["curriculum_version_id"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_framework_id",
        "learning_outcome_competency_links",
        ["framework_id"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_learning_outcome_id",
        "learning_outcome_competency_links",
        ["learning_outcome_id"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_publication_status",
        "learning_outcome_competency_links",
        ["publication_status"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_review_status",
        "learning_outcome_competency_links",
        ["review_status"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_source_revision_id",
        "learning_outcome_competency_links",
        ["source_revision_id"],
        unique=False,
    )
    index(
        "ix_learning_outcome_competency_links_status",
        "learning_outcome_competency_links",
        ["status"],
        unique=False,
    )
    return metadata
