from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine

from app.source_legacy_repair import apply_mapping, inspect_pending

REV_0005 = "20261002_0005"
REV_0006 = "20261003_0006"
REV_0007 = "20261003_0007"
REV_HEAD = "20261007_0010"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_alembic(
    database_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    return subprocess.run(
        ["alembic", "-c", str(backend_root / "alembic.ini"), *args],
        cwd=backend_root,
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )


def _revision(database_path: Path) -> str:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        connection.close()


def _source_columns(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(sources)").fetchall()
        }
    finally:
        connection.close()


def _source_snapshot(
    *,
    source_type: str = "official_syllabus",
    title: str = "Legacy official syllabus",
    academic_year: str = "2026-27",
) -> dict[str, object]:
    return {
        "source_type": source_type,
        "title": title,
        "url": None,
        "authority": "Synthetic Authority",
        "country": "IN",
        "board_or_exam": "SYNTH",
        "academic_year": academic_year,
        "effective_date": None,
        "copyright_classification": "official-public-document",
        "trust_tier": "official_primary",
        "anythingllm_workspace": None,
    }


def _insert_source_0005(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    source_type: str,
    title: str,
    metadata: dict[str, object] | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    trust_tier = {
        "institution_content": "institution",
        "teacher_content": "teacher",
    }.get(source_type, "official_primary")
    authority = (
        None
        if source_type in {"institution_content", "teacher_content"}
        else "Synthetic Authority"
    )
    connection.execute(
        """
        INSERT INTO sources (
            id, source_type, title, url, authority, country, board_or_exam,
            academic_year, effective_date, retrieved_at, checksum,
            copyright_classification, trust_tier, anythingllm_workspace,
            status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            source_type,
            title,
            None,
            authority,
            "IN",
            "SYNTH",
            "2026-27",
            None,
            None,
            None,
            "synthetic",
            trust_tier,
            None,
            "staged",
            json.dumps(metadata or {}),
            now,
            now,
        ),
    )


def _insert_revision_0005(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    revision_number: int,
    status: str,
    ingestion_method: str = "json",
    manual_metadata: dict[str, object] | None = None,
) -> tuple[str, str, str]:
    revision_id = str(uuid4())
    snapshot = _source_snapshot()
    if ingestion_method == "manual":
        payload = manual_metadata or {"legacy": revision_number}
        content = _canonical_bytes(payload)
        metadata: dict[str, object] = {
            "source_snapshot": snapshot,
            "manual_metadata": payload,
        }
        content_type = "application/vnd.eduvijna.metadata+json"
        storage_path = None
        original_filename = None
    else:
        content = _canonical_bytes({"revision": revision_number})
        metadata = {"source_snapshot": snapshot}
        content_type = "application/json"
        storage_path = f"{source_id}/{revision_number}.json"
        original_filename = "source.json"

    checksum = _sha256(content)
    now = datetime.now(UTC).isoformat()
    extraction_status = (
        "pending" if status in {"staged", "failed"} else "succeeded"
    )
    extracted_text = (
        None
        if extraction_status == "pending"
        else content.decode("utf-8")
    )
    active_slot = 1 if status == "active" else None
    approved_by = "founder" if status in {"approved", "active", "superseded"} else None
    approved_at = now if approved_by else None
    activated_at = now if status in {"active", "superseded"} else None
    superseded_at = now if status == "superseded" else None

    connection.execute(
        """
        INSERT INTO source_revisions (
            id, source_id, revision_number, ingestion_method, checksum,
            content_type, byte_size, storage_path, original_filename,
            retrieved_at, extraction_status, extracted_text,
            extraction_metadata_json, status, active_slot, failure_reason,
            approved_by, approved_at, activated_at, superseded_at,
            anythingllm_document_id, metadata_json, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            revision_id,
            source_id,
            revision_number,
            ingestion_method,
            checksum,
            content_type,
            len(content),
            storage_path,
            original_filename,
            now,
            extraction_status,
            extracted_text,
            "{}",
            status,
            active_slot,
            None,
            approved_by,
            approved_at,
            activated_at,
            superseded_at,
            None,
            json.dumps(metadata),
            now,
            now,
        ),
    )
    return revision_id, checksum, _sha256(_canonical_bytes(snapshot))


def _insert_tenancy_0005(connection: sqlite3.Connection) -> tuple[str, str, str]:
    now = datetime.now(UTC).isoformat()
    organization_id = str(uuid4())
    institution_id = str(uuid4())
    teacher_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO organizations (
            id, code, name, active, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (organization_id, "legacy-org", "Legacy Org", 1, "{}", now, now),
    )
    connection.execute(
        """
        INSERT INTO institutions (
            id, organization_id, code, name, active, metadata_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            institution_id,
            organization_id,
            "legacy-inst",
            "Legacy Institution",
            1,
            "{}",
            now,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO teachers (
            id, institution_id, external_code, display_name, active,
            metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            teacher_id,
            institution_id,
            "legacy-teacher",
            "Legacy Teacher",
            1,
            "{}",
            now,
            now,
        ),
    )
    return organization_id, institution_id, teacher_id


def test_0005_revision_states_are_migrated_with_real_snapshot_hashes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-revision-states.db"
    _run_alembic(database_path, "upgrade", REV_0005)

    source_id = str(uuid4())
    statuses = ["staged", "extracted", "validated", "approved", "active", "superseded"]
    inserted: dict[str, tuple[str, str, str]] = {}
    connection = sqlite3.connect(database_path)
    try:
        _insert_source_0005(
            connection,
            source_id=source_id,
            source_type="official_syllabus",
            title="Legacy official syllabus",
        )
        for number, status in enumerate(statuses, start=1):
            inserted[status] = _insert_revision_0005(
                connection,
                source_id=source_id,
                revision_number=number,
                status=status,
            )
        manual_id, manual_checksum, manual_snapshot = _insert_revision_0005(
            connection,
            source_id=source_id,
            revision_number=7,
            status="approved",
            ingestion_method="manual",
            manual_metadata={"manual": "legacy"},
        )
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database_path, "upgrade", "head")
    assert _revision(database_path) == REV_HEAD

    connection = sqlite3.connect(database_path)
    try:
        for status, (revision_id, checksum, snapshot_checksum) in inserted.items():
            row = connection.execute(
                """
                SELECT status, extraction_status, extracted_text,
                       source_snapshot_checksum, extracted_checksum,
                       validated_checksum, approval_fingerprint, approved_by
                FROM source_revisions
                WHERE id = ?
                """,
                (revision_id,),
            ).fetchone()
            assert row is not None
            migrated_status = str(row[0])
            assert row[3] == snapshot_checksum
            assert row[3] != checksum
            assert row[6] is None

            if status in {"extracted", "validated", "approved"}:
                assert migrated_status == "staged"
                assert row[1] == "pending"
                assert row[2] is None
                assert row[4] is None
                assert row[5] is None
                assert row[7] is None
            elif status == "staged":
                assert migrated_status == "staged"
                assert row[4] is None
                assert row[5] is None
            else:
                assert migrated_status == status
                assert row[4] == checksum
                assert row[5] == checksum

        manual_row = connection.execute(
            """
            SELECT status, source_snapshot_checksum, extracted_checksum,
                   validated_checksum, approval_fingerprint, approved_by
            FROM source_revisions
            WHERE id = ?
            """,
            (manual_id,),
        ).fetchone()
        assert manual_row == (
            "extracted",
            manual_snapshot,
            manual_checksum,
            None,
            None,
            None,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_existing_old_0006_bad_backfill_is_repaired_by_0007(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "already-0006.db"
    _run_alembic(database_path, "upgrade", REV_0005)

    source_id = str(uuid4())
    connection = sqlite3.connect(database_path)
    try:
        _insert_source_0005(
            connection,
            source_id=source_id,
            source_type="official_syllabus",
            title="Legacy official syllabus",
        )
        revision_id, checksum, snapshot_checksum = _insert_revision_0005(
            connection,
            source_id=source_id,
            revision_number=1,
            status="staged",
        )
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database_path, "upgrade", REV_0006)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            UPDATE source_revisions
            SET source_snapshot_checksum = ?,
                status = 'approved',
                extraction_status = 'succeeded',
                extracted_text = '{"legacy":true}',
                extracted_checksum = ?,
                validated_checksum = ?,
                approval_fingerprint = NULL,
                approved_by = 'founder',
                approved_at = ?
            WHERE id = ?
            """,
            (
                checksum,
                checksum,
                checksum,
                datetime.now(UTC).isoformat(),
                revision_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    _run_alembic(database_path, "upgrade", "head")

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT status, extraction_status, extracted_text,
                   source_snapshot_checksum, extracted_checksum,
                   validated_checksum, approval_fingerprint, approved_by
            FROM source_revisions
            WHERE id = ?
            """,
            (revision_id,),
        ).fetchone()
        assert row == (
            "staged",
            "pending",
            None,
            snapshot_checksum,
            None,
            None,
            None,
            None,
        )
    finally:
        connection.close()


def test_legacy_tenant_sources_require_explicit_repair_then_upgrade(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-tenant-source.db"
    _run_alembic(database_path, "upgrade", REV_0005)

    institution_source_id = str(uuid4())
    teacher_source_id = str(uuid4())
    connection = sqlite3.connect(database_path)
    try:
        organization_id, institution_id, teacher_id = _insert_tenancy_0005(connection)
        _insert_source_0005(
            connection,
            source_id=institution_source_id,
            source_type="institution_content",
            title="Legacy institution source",
        )
        _insert_source_0005(
            connection,
            source_id=teacher_source_id,
            source_type="teacher_content",
            title="Legacy teacher source",
        )
        connection.commit()
    finally:
        connection.close()

    failed = _run_alembic(database_path, "upgrade", "head", check=False)
    assert failed.returncode != 0
    assert institution_source_id in (failed.stdout + failed.stderr)
    assert teacher_source_id in (failed.stdout + failed.stderr)
    assert _revision(database_path) == REV_0005
    assert "organization_id" not in _source_columns(database_path)

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        pending = inspect_pending(connection)
    assert {item["source_id"] for item in pending} == {
        institution_source_id,
        teacher_source_id,
    }
    assert all(item["repair_staged"] is False for item in pending)

    mapping_path = tmp_path / "ownership.json"
    mapping_path.write_text(
        json.dumps(
            {
                institution_source_id: {
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "teacher_id": None,
                },
                teacher_source_id: {
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "teacher_id": teacher_id,
                },
            }
        ),
        encoding="utf-8",
    )
    with engine.begin() as connection:
        updated = apply_mapping(connection, mapping_path)
    assert set(updated) == {institution_source_id, teacher_source_id}

    _run_alembic(database_path, "upgrade", "head")
    assert _revision(database_path) == REV_HEAD

    connection = sqlite3.connect(database_path)
    try:
        institution_row = connection.execute(
            """
            SELECT organization_id, institution_id, teacher_id
            FROM sources
            WHERE id = ?
            """,
            (institution_source_id,),
        ).fetchone()
        assert institution_row == (organization_id, institution_id, None)

        teacher_row = connection.execute(
            """
            SELECT organization_id, institution_id, teacher_id
            FROM sources
            WHERE id = ?
            """,
            (teacher_source_id,),
        ).fetchone()
        assert teacher_row == (organization_id, institution_id, teacher_id)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_invalid_legacy_ownership_mapping_is_rejected_before_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "invalid-legacy-owner.db"
    _run_alembic(database_path, "upgrade", REV_0005)

    source_id = str(uuid4())
    connection = sqlite3.connect(database_path)
    try:
        organization_id, institution_id, _ = _insert_tenancy_0005(connection)
        _insert_source_0005(
            connection,
            source_id=source_id,
            source_type="teacher_content",
            title="Legacy teacher source",
        )
        connection.commit()
    finally:
        connection.close()

    mapping_path = tmp_path / "invalid-ownership.json"
    mapping_path.write_text(
        json.dumps(
            {
                source_id: {
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "teacher_id": str(uuid4()),
                }
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            try:
                apply_mapping(connection, mapping_path)
            except ValueError as exc:
                assert "teacher does not belong" in str(exc)
            else:
                raise AssertionError("invalid ownership mapping was accepted")
    finally:
        engine.dispose()

    assert _revision(database_path) == REV_0005
    assert "organization_id" not in _source_columns(database_path)
