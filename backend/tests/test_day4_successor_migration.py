"""Upgrade issued 0008 variants without overwriting migration history or evidence."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.curriculum_intelligence.framework_structure import FrameworkStructureService
from app.db.session import create_database_engine
from app.models.curriculum import CurriculumNode
from app.models.curriculum_intelligence import AssessmentEvidence
from app.models.source import SourceAuditEvent
from tests.test_day4_framework_structure import _context, _link_input, _tree

BACKEND = Path(__file__).resolve().parents[1]
PREVIOUS = "20261004_0008"
HEAD = "20261007_0010"
TABLES = ("framework_structure_nodes", "learning_outcome_competency_links")


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "framework_migration",
        BACKEND / "migrations/versions/20261004_0009_framework_and_marking_scheme.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alembic(database: Path, *args: str, success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{database}"},
        capture_output=True,
        text=True,
    )
    if success:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
    return result


def _seed_legacy(database: Path, *, adopted: bool = False) -> dict[str, str]:
    _alembic(database, "upgrade", PREVIOUS)
    engine = create_database_engine(f"sqlite:///{database}")
    assert not set(TABLES).intersection(sa.inspect(engine).get_table_names())
    if adopted:
        # This is the exact frozen framework table shape temporarily issued in 0008.
        metadata = _migration()._framework_metadata()
        with engine.begin() as connection:
            for name in TABLES:
                metadata.tables[name].create(connection)
    with Session(engine) as session:
        context = _context(session)
        scheme = _context(session, "scheme")
        scheme.revision.metadata_json = {"source_snapshot": {"source_type": "marking_scheme"}}
        grade = CurriculumNode(
            curriculum_version_id=context.version.id,
            code="X",
            title="Class X",
            node_type="grade_year",
        )
        session.add(grade)
        session.flush()
        medium = CurriculumNode(
            curriculum_version_id=context.version.id,
            code="English",
            title="English",
            node_type="medium",
            parent_id=grade.id,
            parent_version_id=context.version.id,
        )
        session.add(medium)
        session.flush()
        subject = CurriculumNode(
            curriculum_version_id=context.version.id,
            code="Maths",
            title="Mathematics",
            node_type="subject",
            parent_id=medium.id,
            parent_version_id=context.version.id,
        )
        session.add(subject)
        session.flush()
        audit = SourceAuditEvent(
            source_id=scheme.revision.source_id,
            source_revision_id=scheme.revision.id,
            event_type="synthetic_migration_audit",
            outcome="success",
            actor_id="synthetic-reviewer",
            payload_json={"retain": True},
        )
        session.add(audit)
        session.flush()
        nodes = _tree(session, context) if adopted else {}
        if adopted:
            FrameworkStructureService(session).link_learning_outcome(
                _link_input(context, nodes["C3.2"].id)
            )
        ids = {
            "revision": context.revision.id,
            "scheme": scheme.revision.id,
            "version": context.version.id,
            "grade": grade.id,
            "subject": subject.id,
            "audit": audit.id,
            "evidence": str(uuid4()),
            "framework_node": nodes["C3.2"].id if nodes else "",
        }
        session.commit()
    evidence = sa.Table("assessment_evidence", sa.MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            evidence.insert().values(
                id=ids["evidence"],
                curriculum_version_id=ids["version"],
                source_revision_id=ids["revision"],
                grade_node_id=ids["grade"],
                subject_node_id=ids["subject"],
                evidence_type="sample_question_paper",
                source_locator="synthetic p. 1",
                evidence_json={"retain_evidence": [1, 2, 3]},
                metadata_json={
                    "marking_scheme_revision_id": ids["scheme"],
                    "retain_metadata": True,
                },
                created_at=datetime(2026, 10, 4, tzinfo=UTC),
                updated_at=datetime(2026, 10, 4, tzinfo=UTC),
            )
        )
    engine.dispose()
    return ids


def _rows(database: Path, table: str) -> list[dict[str, Any]]:
    engine = create_database_engine(f"sqlite:///{database}")
    reflected = sa.Table(table, sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        result = [dict(row) for row in connection.execute(sa.select(reflected)).mappings()]
    engine.dispose()
    return result


@pytest.mark.parametrize("adopted", [False, True])
def test_0009_upgrades_both_issued_0008_shapes_and_preserves_data(
    tmp_path: Path, adopted: bool
) -> None:
    database = tmp_path / "compatible.db"
    ids = _seed_legacy(database, adopted=adopted)
    before = _rows(database, "assessment_evidence")
    audits = _rows(database, "source_audit_events")
    framework_rows = {name: _rows(database, name) for name in TABLES} if adopted else {}
    settings_before = _rows(database, "system_settings")
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    after = _rows(database, "assessment_evidence")
    assert after[0].pop("marking_scheme_revision_id") == ids["scheme"]
    assert after == before
    assert _rows(database, "source_audit_events") == audits
    ownership = [
        row
        for row in _rows(database, "system_settings")
        if row["key"] == _migration()._OWNERSHIP_KEY
    ]
    assert len(ownership) == 1
    assert ownership[0]["value"] == ("adopted" if adopted else "created")
    if adopted:
        assert all(framework_rows.values())  # Both tables contain pre-existing evidence.
        assert {name: _rows(database, name) for name in TABLES} == framework_rows
    _alembic(database, "downgrade", PREVIOUS)
    assert _rows(database, "assessment_evidence") == before
    engine = create_database_engine(f"sqlite:///{database}")
    if adopted:
        assert set(TABLES) <= set(sa.inspect(engine).get_table_names())
        assert {name: _rows(database, name) for name in TABLES} == framework_rows
    else:
        assert not set(TABLES).intersection(sa.inspect(engine).get_table_names())
    assert _rows(database, "system_settings") == settings_before
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    assert _rows(database, "assessment_evidence")[0]["marking_scheme_revision_id"] == ids["scheme"]
    assert _rows(database, "source_audit_events") == audits
    if adopted:
        assert {name: _rows(database, name) for name in TABLES} == framework_rows
    _alembic(database, "downgrade", PREVIOUS)
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    if adopted:
        assert {name: _rows(database, name) for name in TABLES} == framework_rows
    engine.dispose()


@pytest.mark.parametrize("damage", ["partial", "index", "columns", "check"])
def test_0009_rejects_incompatible_preexisting_framework_schema_atomically(
    tmp_path: Path, damage: str
) -> None:
    database = tmp_path / "incompatible.db"
    _seed_legacy(database, adopted=True)
    engine = create_database_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        if damage == "partial":
            connection.exec_driver_sql("DROP TABLE learning_outcome_competency_links")
        elif damage == "index":
            connection.exec_driver_sql("DROP INDEX ix_framework_structure_nodes_level")
        elif damage == "columns":
            connection.exec_driver_sql(
                "ALTER TABLE framework_structure_nodes ADD COLUMN unknown TEXT"
            )
        else:
            # Mutate the constraint while retaining its name to test semantic validation.
            connection.exec_driver_sql("PRAGMA writable_schema=ON")
            connection.exec_driver_sql(
                "UPDATE sqlite_master SET sql=replace(sql, "
                "'level IN (''stage'', ''curricular_area'', ''goal'', ''competency'')', "
                "'level IS NOT NULL') WHERE name='framework_structure_nodes'"
            )
            connection.exec_driver_sql("PRAGMA writable_schema=OFF")
    engine.dispose()
    before = _rows(database, "assessment_evidence")
    result = _alembic(database, "upgrade", "head", success=False)
    assert "cannot adopt" in result.stderr
    assert _rows(database, "assessment_evidence") == before
    assert _rows(database, "alembic_version") == [{"version_num": PREVIOUS}]


@pytest.mark.parametrize("bad_reference", ["missing", "wrong_domain", "object"])
def test_0009_rejects_invalid_legacy_marking_scheme_reference_without_partial_changes(
    tmp_path: Path, bad_reference: str
) -> None:
    database = tmp_path / "invalid-ms.db"
    ids = _seed_legacy(database)
    engine = create_database_engine(f"sqlite:///{database}")
    table = sa.Table("assessment_evidence", sa.MetaData(), autoload_with=engine)
    value: Any = str(uuid4()) if bad_reference == "missing" else ids["revision"]
    if bad_reference == "object":
        value = {"invalid": True}
    with engine.begin() as connection:
        if bad_reference == "wrong_domain":
            revisions = sa.Table("source_revisions", sa.MetaData(), autoload_with=connection)
            connection.execute(
                revisions.update()
                .where(revisions.c.id == ids["revision"])
                .values(metadata_json={"source_snapshot": {"source_type": "sample_paper"}})
            )
        connection.execute(
            table.update().values(metadata_json={"marking_scheme_revision_id": value})
        )
    before = _rows(database, "assessment_evidence")
    _alembic(database, "upgrade", "head", success=False)
    assert _rows(database, "assessment_evidence") == before
    assert _rows(database, "alembic_version") == [{"version_num": PREVIOUS}]
    assert not set(TABLES).intersection(sa.inspect(engine).get_table_names())
    engine.dispose()


def test_0009_rolls_back_schema_changes_after_database_failure_then_retries(tmp_path: Path) -> None:
    database = tmp_path / "retry.db"
    _seed_legacy(database)
    engine = create_database_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE INDEX ix_assessment_evidence_marking_scheme_revision_id ON sources(source_type)"
        )
    before = _rows(database, "assessment_evidence")
    settings_before = _rows(database, "system_settings")
    _alembic(database, "upgrade", "head", success=False)
    assert _rows(database, "assessment_evidence") == before
    assert _rows(database, "system_settings") == settings_before
    assert _rows(database, "alembic_version") == [{"version_num": PREVIOUS}]
    assert not set(TABLES).intersection(sa.inspect(engine).get_table_names())
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_assessment_evidence_marking_scheme_revision_id")
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    engine.dispose()


def test_distinct_marking_scheme_evidence_survives_failed_lossy_downgrade(tmp_path: Path) -> None:
    database = tmp_path / "distinct-ms.db"
    ids = _seed_legacy(database)
    _alembic(database, "upgrade", "head")
    engine = create_database_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        other = _context(session, "other-scheme")
        other.revision.metadata_json = {"source_snapshot": {"source_type": "marking_scheme"}}
        session.add(
            AssessmentEvidence(
                curriculum_version_id=ids["version"],
                source_revision_id=ids["revision"],
                marking_scheme_revision_id=other.revision.id,
                grade_node_id=ids["grade"],
                subject_node_id=ids["subject"],
                evidence_type="sample_question_paper",
                source_locator="synthetic p. 1",
                evidence_json={"changed_ms": True},
                metadata_json={},
            )
        )
        session.commit()
    before = _rows(database, "assessment_evidence")
    assert len(before) == 2
    result = _alembic(database, "downgrade", PREVIOUS, success=False)
    assert "collapse distinct marking-scheme evidence" in result.stderr
    assert _rows(database, "assessment_evidence") == before
    assert _rows(database, "alembic_version") == [{"version_num": HEAD}]
    assert set(TABLES) <= set(sa.inspect(engine).get_table_names())
    engine.dispose()


def test_0009_downgrade_preserves_new_marking_scheme_binding_in_metadata(tmp_path: Path) -> None:
    database = tmp_path / "preserve-new-binding.db"
    ids = _seed_legacy(database)
    _alembic(database, "upgrade", "head")
    engine = create_database_engine(f"sqlite:///{database}")
    evidence = sa.Table("assessment_evidence", sa.MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(evidence.update().values(metadata_json={"unrelated": "retain"}))
    before = _rows(database, "assessment_evidence")[0]
    _alembic(database, "downgrade", PREVIOUS)
    legacy = _rows(database, "assessment_evidence")[0]
    assert legacy["id"] == before["id"]
    assert legacy["metadata_json"] == {
        "unrelated": "retain",
        "marking_scheme_revision_id": ids["scheme"],
    }
    assert legacy["created_at"] == before["created_at"]
    assert legacy["updated_at"] == before["updated_at"]
    _alembic(database, "upgrade", "head")
    assert _rows(database, "assessment_evidence")[0]["marking_scheme_revision_id"] == ids["scheme"]
    engine.dispose()


@pytest.mark.parametrize("collision", ["key", "id"])
def test_0009_ownership_collision_does_not_overwrite_settings_and_can_retry(
    tmp_path: Path, collision: str
) -> None:
    database = tmp_path / "ownership-collision.db"
    _seed_legacy(database, adopted=True)
    migration = _migration()
    engine = create_database_engine(f"sqlite:///{database}")
    settings = sa.Table("system_settings", sa.MetaData(), autoload_with=engine)
    conflicting_id = migration._OWNERSHIP_ID if collision == "id" else str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            settings.insert().values(
                id=conflicting_id,
                key=migration._OWNERSHIP_KEY if collision == "key" else "unrelated.user.setting",
                value="retain original value",
                created_at=datetime.now(UTC),
            )
        )
    before = _rows(database, "system_settings")
    evidence = {name: _rows(database, name) for name in TABLES}
    result = _alembic(database, "upgrade", "head", success=False)
    assert "ownership marker collides" in result.stderr
    assert _rows(database, "system_settings") == before
    assert {name: _rows(database, name) for name in TABLES} == evidence
    assert _rows(database, "alembic_version") == [{"version_num": PREVIOUS}]
    with engine.begin() as connection:
        connection.execute(settings.delete().where(settings.c.id == conflicting_id))
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    _alembic(database, "downgrade", PREVIOUS)
    assert {name: _rows(database, name) for name in TABLES} == evidence
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    engine.dispose()


@pytest.mark.parametrize("damage", ["missing", "value", "id", "key"])
def test_0009_unknown_ownership_blocks_downgrade_without_destroying_evidence(
    tmp_path: Path, damage: str
) -> None:
    database = tmp_path / "unknown-ownership.db"
    _seed_legacy(database, adopted=True)
    _alembic(database, "upgrade", "head")
    migration = _migration()
    engine = create_database_engine(f"sqlite:///{database}")
    settings = sa.Table("system_settings", sa.MetaData(), autoload_with=engine)
    original = next(
        row for row in _rows(database, "system_settings") if row["key"] == migration._OWNERSHIP_KEY
    )
    replacements = {"value": "unknown", "id": str(uuid4()), "key": "unexpected.key"}
    with engine.begin() as connection:
        statement = (
            settings.delete()
            if damage == "missing"
            else settings.update().values({damage: replacements[damage]})
        )
        connection.execute(statement.where(settings.c.key == migration._OWNERSHIP_KEY))
    before = _rows(database, "system_settings")
    framework_rows = {name: _rows(database, name) for name in TABLES}
    evidence = _rows(database, "assessment_evidence")
    result = _alembic(database, "downgrade", PREVIOUS, success=False)
    assert "cannot safely determine framework table ownership" in result.stderr
    assert _rows(database, "system_settings") == before
    assert {name: _rows(database, name) for name in TABLES} == framework_rows
    assert _rows(database, "assessment_evidence") == evidence
    assert _rows(database, "alembic_version") == [{"version_num": HEAD}]
    with engine.begin() as connection:
        damaged_id = replacements["id"] if damage == "id" else original["id"]
        connection.execute(settings.delete().where(settings.c.id == damaged_id))
        connection.execute(settings.insert().values(**original))
    _alembic(database, "downgrade", PREVIOUS)
    assert {name: _rows(database, name) for name in TABLES} == framework_rows
    _alembic(database, "upgrade", "head")
    _alembic(database, "check")
    engine.dispose()
