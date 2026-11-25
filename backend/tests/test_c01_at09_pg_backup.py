"""AT09 — PostgreSQL pg_dump/restore on exclusively owned disposable databases."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from tests.c01_at_support import (
    REV_0020,
    REV_0021,
    canonical_row_digest,
    drop_owned_pg_database,
    ensure_owned_disposable_pg_url,
    insert_pg_replay_at_0020,
    now_iso,
    owned_pg_database_name,
    run_alembic_url,
)
from tests.c01_disposable_pg import C01_PG_OPT_IN


def _pg_tools_available() -> bool:
    return shutil.which("pg_dump") is not None and shutil.which("psql") is not None


def _seed_populated_after_0021(conn, *, org_id: str, inst_id: str) -> dict[str, int]:
    ts = now_iso()
    source_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO sources (
                id, source_type, title, trust_tier, status, metadata_json,
                created_at, updated_at
            ) VALUES (
                :id, 'official_syllabus', 'AT09 source', 'official_primary',
                'active', '{}'::json, CAST(:ts AS timestamptz), CAST(:ts AS timestamptz)
            )
            """
        ),
        {"id": source_id, "ts": ts},
    )
    conn.execute(
        text(
            """
            INSERT INTO source_revisions (
                id, source_id, revision_number, ingestion_method, checksum,
                source_snapshot_checksum, content_type, byte_size, retrieved_at,
                extraction_status, extraction_metadata_json, status, active_slot,
                metadata_json, created_at, updated_at
            ) VALUES (
                :id, :source, 1, 'manual', :csum, :ssum, 'application/pdf', 42,
                CAST(:ts AS timestamptz), 'validated', '{}'::json, 'active', 1,
                '{}'::json, CAST(:ts AS timestamptz), CAST(:ts AS timestamptz)
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "source": source_id,
            "csum": "c" * 64,
            "ssum": "d" * 64,
            "ts": ts,
        },
    )
    return {
        "organizations": 1,
        "institutions": 1,
        "sources": 1,
        "source_revisions": 1,
        "d13_replay_reservations": 1,
    }


@pytest.mark.c01_at09
def test_at09_pg_dump_restore_roundtrip() -> None:
    if os.environ.get(C01_PG_OPT_IN) != "1":
        pytest.skip(f"{C01_PG_OPT_IN}=1 required")
    if not _pg_tools_available():
        pytest.skip("pg_dump/psql not available — BLOCKED infrastructure")
    _, _, admin_url = ensure_owned_disposable_pg_url()
    src_name = owned_pg_database_name("c01_at09_src")
    dst_name = owned_pg_database_name("c01_at09_dst")
    from tests.c01_at_support import create_owned_pg_database

    src_url = create_owned_pg_database(admin_url, src_name)
    dst_url = create_owned_pg_database(admin_url, dst_name)
    dump_path = Path("/tmp") / f"{src_name}.sql"
    try:
        assert run_alembic_url(src_url, "upgrade", REV_0020).returncode == 0
        org_id = str(uuid.uuid4())
        inst_id = str(uuid.uuid4())
        ts = now_iso()
        engine = create_engine(src_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO organizations (
                        id, code, name, active, metadata_json, created_at, updated_at
                    ) VALUES (
                        :id, 'AT-ORG', 'AT Org', true, '{}'::json,
                        CAST(:ts AS timestamptz), CAST(:ts AS timestamptz)
                    )
                    """
                ),
                {"id": org_id, "ts": ts},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO institutions (
                        id, organization_id, code, name, active, metadata_json,
                        created_at, updated_at
                    ) VALUES (
                        :id, :org, 'AT-INST', 'AT Inst', true, '{}'::json,
                        CAST(:ts AS timestamptz), CAST(:ts AS timestamptz)
                    )
                    """
                ),
                {"id": inst_id, "org": org_id, "ts": ts},
            )
            insert_pg_replay_at_0020(conn, org_id=org_id, inst_id=inst_id)
        assert run_alembic_url(src_url, "upgrade", REV_0021).returncode == 0
        before_hashes: dict[str, str] = {}
        with engine.begin() as conn:
            counts = _seed_populated_after_0021(conn, org_id=org_id, inst_id=inst_id)
            for table, expected in counts.items():
                rows = conn.execute(text(f"SELECT * FROM {table} ORDER BY 1")).fetchall()
                assert len(rows) >= expected, f"{table} must be nonempty"
                before_hashes[table] = canonical_row_digest([tuple(r) for r in rows])
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == REV_0021

        parsed = urlparse(src_url)
        env = os.environ.copy()
        env["PGPASSWORD"] = parsed.password or ""
        dump = subprocess.run(
            [
                "pg_dump",
                "-h",
                parsed.hostname or "127.0.0.1",
                "-p",
                str(parsed.port or 5432),
                "-U",
                parsed.username or "postgres",
                "-d",
                src_name,
                "-f",
                str(dump_path),
            ],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert dump.returncode == 0, dump.stderr
        restore = subprocess.run(
            [
                "psql",
                "-h",
                parsed.hostname or "127.0.0.1",
                "-p",
                str(parsed.port or 5432),
                "-U",
                parsed.username or "postgres",
                "-d",
                dst_name,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(dump_path),
            ],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert restore.returncode == 0, restore.stderr
        with create_engine(dst_url).connect() as conn:
            for table, digest in before_hashes.items():
                rows = conn.execute(text(f"SELECT * FROM {table} ORDER BY 1")).fetchall()
                after = canonical_row_digest([tuple(r) for r in rows])
                assert after == digest, table
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == REV_0021
    finally:
        dump_path.unlink(missing_ok=True)
        drop_owned_pg_database(admin_url, src_name)
        drop_owned_pg_database(admin_url, dst_name)