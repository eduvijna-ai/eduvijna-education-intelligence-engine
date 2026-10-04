from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import SourceRevision
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

REV_0006 = "20261003_0006"
REV_0007 = "20261003_0007"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _run_alembic(
    database: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    backend = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["alembic", "-c", str(backend / "alembic.ini"), *args],
        cwd=backend,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{database}"},
        check=check,
        capture_output=True,
        text=True,
    )


def _seed_collision(
    database: Path, *, status: str = "active", method: str = "json"
) -> dict[str, object]:
    _run_alembic(database, "upgrade", REV_0006)
    engine = sa.create_engine(f"sqlite:///{database}")
    tables = sa.MetaData()
    tables.reflect(engine)
    now = datetime.now(UTC)
    timestamps = {"created_at": now, "updated_at": now}
    snapshot: dict[str, object] = {
        "source_type": "official_syllabus",
        "title": "Synthetic migration collision fixture",
        "authority": "Synthetic Authority",
        "trust_tier": "official_primary",
        "metadata_json": {"synthetic": True},
    }
    content = {"synthetic": "same bytes re-ingested after old 0006"}
    metadata: dict[str, Any] = {"source_snapshot": snapshot, "retained": "metadata"}
    if method == "manual":
        metadata["manual_metadata"] = content
    checksum = _checksum(content)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.execute(
                tables.tables["sources"]
                .insert()
                .values(
                    id="source",
                    source_type="official_syllabus",
                    title=snapshot["title"],
                    authority=snapshot["authority"],
                    trust_tier="official_primary",
                    status="active" if status == "active" else "staged",
                    metadata_json={"synthetic": True},
                    **timestamps,
                )
            )
            for number, revision_id in enumerate(("legacy", "canonical"), start=1):
                revision_status = status if revision_id == "legacy" else "approved"
                connection.execute(
                    tables.tables["source_revisions"]
                    .insert()
                    .values(
                        id=revision_id,
                        source_id="source",
                        revision_number=number,
                        ingestion_method=method,
                        checksum=checksum,
                        source_snapshot_checksum=(checksum if number == 1 else _checksum(snapshot)),
                        content_type="application/json",
                        byte_size=len(_canonical_bytes(content)),
                        storage_path=f"source/{revision_id}.json",
                        original_filename="source.json",
                        retrieved_at=now,
                        extraction_status="succeeded",
                        extracted_text=json.dumps(content),
                        extracted_checksum=checksum,
                        validated_checksum=checksum,
                        approval_fingerprint="a" * 64,
                        extraction_metadata_json={"retained": revision_id},
                        status=revision_status,
                        active_slot=1 if revision_status == "active" else None,
                        approved_by="founder",
                        approved_at=now,
                        activated_at=now if revision_status in {"active", "superseded"} else None,
                        superseded_at=now if revision_status == "superseded" else None,
                        metadata_json=metadata,
                        **timestamps,
                    )
                )
                connection.execute(
                    tables.tables["source_audit_events"]
                    .insert()
                    .values(
                        id=f"audit-{revision_id}",
                        source_id="source",
                        source_revision_id=revision_id,
                        event_type="source_approved",
                        actor_id="founder",
                        outcome="success",
                        payload_json={"original_revision_id": revision_id},
                        **timestamps,
                    )
                )
            connection.execute(
                tables.tables["source_diffs"]
                .insert()
                .values(
                    id="diff",
                    source_id="source",
                    from_revision_id="legacy",
                    to_revision_id="canonical",
                    checksum_changed=False,
                    metadata_changes_json={},
                    content_diff_json={"retained": True},
                    **timestamps,
                )
            )
            for prefix in ("curriculum", "exam"):
                connection.execute(
                    tables.tables[f"{prefix}_packs"]
                    .insert()
                    .values(
                        id=f"{prefix}-pack",
                        code=f"synthetic-{prefix}",
                        name="Synthetic fixture",
                        country="IN",
                        active=True,
                        metadata_json={},
                        **timestamps,
                    )
                )
                connection.execute(
                    tables.tables[f"{prefix}_versions"]
                    .insert()
                    .values(
                        id=f"{prefix}-version",
                        **{f"{prefix}_pack_id": f"{prefix}-pack"},
                        version_code="synthetic",
                        status="draft",
                        metadata_json={},
                        **timestamps,
                    )
                )
            connection.execute(
                tables.tables["questions"]
                .insert()
                .values(
                    id="question",
                    content_version=1,
                    origin_type="generated",
                    question_type="descriptive",
                    stem_text="Synthetic fixture",
                    answer_json={},
                    grade_year_codes=[],
                    rubric_json={},
                    status="draft",
                    metadata_json={},
                    **timestamps,
                )
            )
            connection.execute(
                tables.tables["policy_rules"]
                .insert()
                .values(
                    id="policy",
                    scope_type="global",
                    scope_code="synthetic",
                    policy_key="synthetic",
                    value_json={},
                    priority=0,
                    active=True,
                    metadata_json={},
                    **timestamps,
                )
            )
            for table, column, value in (
                (
                    "curriculum_version_source_revisions",
                    "curriculum_version_id",
                    "curriculum-version",
                ),
                ("exam_version_source_revisions", "exam_version_id", "exam-version"),
                ("question_source_revisions", "question_id", "question"),
                ("policy_rule_source_revisions", "policy_rule_id", "policy"),
            ):
                for revision_id in ("legacy", "canonical"):
                    connection.execute(
                        tables.tables[table]
                        .insert()
                        .values(**{column: value}, source_revision_id=revision_id)
                    )
    finally:
        engine.dispose()
    return snapshot


def _rows(database: Path, table: str) -> list[dict[str, Any]]:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]


@pytest.mark.parametrize("status", ["active", "superseded", "approved", "validated", "extracted"])
@pytest.mark.parametrize("method", ["json", "manual"])
def test_0007_preserves_colliding_revisions_and_all_references(
    tmp_path: Path, status: str, method: str
) -> None:
    database = tmp_path / "collision.db"
    snapshot = _seed_collision(database, status=status, method=method)
    before = {row["id"]: row for row in _rows(database, "source_revisions")}
    unchanged_tables = (
        "sources",
        "source_diffs",
        "source_audit_events",
        "curriculum_version_source_revisions",
        "exam_version_source_revisions",
        "question_source_revisions",
        "policy_rule_source_revisions",
    )
    references = {table: _rows(database, table) for table in unchanged_tables}

    _run_alembic(database, "upgrade", REV_0007)

    after = {row["id"]: row for row in _rows(database, "source_revisions")}
    assert set(after) == set(before)
    assert after["canonical"] == before["canonical"]
    legacy = after["legacy"]
    repaired_metadata = json.loads(legacy["metadata_json"])
    repaired_snapshot = repaired_metadata["source_snapshot"]
    assert all(repaired_snapshot[key] == value for key, value in snapshot.items())
    assert repaired_metadata["retained"] == "metadata"
    assert repaired_snapshot["_eduvijna_legacy_revision_identity"] == {
        "migration_revision": REV_0007,
        "revision_id": "legacy",
        "canonical_revision_id": "canonical",
        "original_source_snapshot_checksum": before["legacy"]["source_snapshot_checksum"],
        "canonical_source_snapshot_checksum": _checksum(snapshot),
    }
    assert legacy["source_snapshot_checksum"] == _checksum(repaired_snapshot)
    assert legacy["source_snapshot_checksum"] != after["canonical"]["source_snapshot_checksum"]
    assert legacy["checksum"] == before["legacy"]["checksum"]
    for column in (
        "id",
        "source_id",
        "revision_number",
        "active_slot",
        "activated_at",
        "superseded_at",
    ):
        assert legacy[column] == before["legacy"][column]
    expected_status = (
        status
        if status in {"active", "superseded"}
        else ("extracted" if method == "manual" else "staged")
    )
    assert legacy["status"] == expected_status
    assert legacy["approval_fingerprint"] is None
    for table in unchanged_tables:
        assert _rows(database, table) == references[table]
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    _run_alembic(database, "downgrade", REV_0006)
    _run_alembic(database, "upgrade", REV_0007)
    assert _rows(database, "source_revisions") == list(after.values())


def test_0007_repairs_all_bad_duplicates_without_overwriting_snapshot_fields(
    tmp_path: Path,
) -> None:
    database = tmp_path / "both-bad.db"
    snapshot = _seed_collision(database)
    snapshot["_eduvijna_legacy_revision_identity"] = {"existing": "must be retained"}
    with sqlite3.connect(database) as connection:
        for revision_id, checksum in (("legacy", "b" * 64), ("canonical", "c" * 64)):
            metadata = json.loads(
                connection.execute(
                    "SELECT metadata_json FROM source_revisions WHERE id = ?", (revision_id,)
                ).fetchone()[0]
            )
            metadata["source_snapshot"] = snapshot
            connection.execute(
                "UPDATE source_revisions SET source_snapshot_checksum = ?, metadata_json = ? "
                "WHERE id = ?",
                (checksum, json.dumps(metadata), revision_id),
            )
    _run_alembic(database, "upgrade", REV_0007)
    rows = {row["id"]: row for row in _rows(database, "source_revisions")}
    assert rows["legacy"]["source_snapshot_checksum"] == _checksum(snapshot)
    repaired_snapshot = json.loads(rows["canonical"]["metadata_json"])["source_snapshot"]
    assert all(repaired_snapshot[key] == value for key, value in snapshot.items())
    assert (
        repaired_snapshot["_eduvijna_legacy_revision_identity_"]["canonical_revision_id"]
        == "legacy"
    )
    assert rows["canonical"]["source_snapshot_checksum"] == _checksum(repaired_snapshot)
    assert rows["canonical"]["status"] == "staged"


def test_0007_handles_transient_identity_collision_when_hashes_are_swapped(tmp_path: Path) -> None:
    database = tmp_path / "swapped.db"
    first_snapshot = _seed_collision(database)
    second_snapshot = {**first_snapshot, "title": "Another retained synthetic snapshot"}
    with sqlite3.connect(database) as connection:
        metadata = json.loads(
            connection.execute(
                "SELECT metadata_json FROM source_revisions WHERE id = 'canonical'"
            ).fetchone()[0]
        )
        metadata["source_snapshot"] = second_snapshot
        connection.execute(
            "UPDATE source_revisions SET source_snapshot_checksum = ? WHERE id = 'legacy'",
            (_checksum(second_snapshot),),
        )
        connection.execute(
            "UPDATE source_revisions SET metadata_json = ? WHERE id = 'canonical'",
            (json.dumps(metadata),),
        )
    _run_alembic(database, "upgrade", REV_0007)
    rows = {row["id"]: row for row in _rows(database, "source_revisions")}
    for revision_id, snapshot in (("legacy", first_snapshot), ("canonical", second_snapshot)):
        assert json.loads(rows[revision_id]["metadata_json"])["source_snapshot"] == snapshot
        assert rows[revision_id]["source_snapshot_checksum"] == _checksum(snapshot)


def test_0007_write_failure_rolls_back_temporary_hashes_and_all_data_then_retries(
    tmp_path: Path,
) -> None:
    database = tmp_path / "rollback.db"
    _seed_collision(database)
    preserved_tables = (
        "alembic_version",
        "source_revisions",
        "source_diffs",
        "source_audit_events",
        "curriculum_version_source_revisions",
        "exam_version_source_revisions",
        "question_source_revisions",
        "policy_rule_source_revisions",
    )
    before = {table: _rows(database, table) for table in preserved_tables}
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_final_identity_repair
            BEFORE UPDATE ON source_revisions
            WHEN NEW.id = 'legacy' AND NEW.metadata_json <> OLD.metadata_json
            BEGIN SELECT RAISE(ABORT, 'injected identity repair failure'); END
            """
        )
    result = _run_alembic(database, "upgrade", REV_0007, check=False)
    assert result.returncode != 0
    assert "injected identity repair failure" in result.stderr
    assert {table: _rows(database, table) for table in preserved_tables} == before
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER fail_final_identity_repair")
    _run_alembic(database, "upgrade", REV_0007)
    assert _rows(database, "alembic_version") == [{"version_num": REV_0007}]
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_repaired_manual_collision_passes_actual_lifecycle_snapshot_validation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "validate-repaired.db"
    _seed_collision(database, status="approved", method="manual")
    _run_alembic(database, "upgrade", REV_0007)
    engine = sa.create_engine(f"sqlite:///{database}")
    try:
        with Session(engine) as session:
            service = SourceIntelligenceService(
                session, storage=LocalSourceStorage(tmp_path / "private")
            )
            service.create_diff("legacy")
            validation = service.validate_revision("legacy")
            assert validation.valid, validation.errors
            assert validation.checks["source_snapshot_integrity"]
            repaired = session.get(SourceRevision, "legacy")
            assert repaired is not None
            canonical = session.get(SourceRevision, "canonical")
            assert canonical is not None
            assert (
                service._find_identity_revision(
                    source_id="source",
                    checksum=repaired.checksum,
                    source_snapshot_checksum=canonical.source_snapshot_checksum,
                )
                is canonical
            )
    finally:
        engine.dispose()
