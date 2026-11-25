"""AT09 — PostgreSQL pg_dump/restore on exclusively owned disposable databases."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.c01_at_support import (
    REV_0021,
    create_owned_pg_database,
    drop_owned_pg_database,
    now_iso,
    owned_pg_database_name,
    pg_admin_url_from_disposable,
    run_alembic_url,
)
from tests.c01_disposable_pg import C01_PG_OPT_IN, validated_disposable_pg_url


def _pg_tools_available() -> bool:
    return shutil.which("pg_dump") is not None and shutil.which("psql") is not None


@pytest.mark.c01_at09
def test_at09_pg_dump_restore_roundtrip() -> None:
    if os.environ.get(C01_PG_OPT_IN) != "1":
        pytest.skip(f"{C01_PG_OPT_IN}=1 required")
    if not _pg_tools_available():
        pytest.skip("pg_dump/psql not available — BLOCKED infrastructure")
    base = validated_disposable_pg_url()
    admin_url = pg_admin_url_from_disposable(base)
    src_name = owned_pg_database_name("c01_at09_src")
    dst_name = owned_pg_database_name("c01_at09_dst")
    src_url = create_owned_pg_database(admin_url, src_name)
    dst_url = create_owned_pg_database(admin_url, dst_name)
    dump_path = Path("/tmp") / f"{src_name}.sql"
    try:
        assert run_alembic_url(src_url, "upgrade", REV_0021).returncode == 0
        engine = create_engine(src_url)
        with engine.begin() as conn:
            ts = now_iso()
            conn.execute(
                text(
                    """
                    INSERT INTO organizations (
                        id, code, name, active, metadata_json, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid()::text, 'AT-ORG', 'AT Org', true, '{}'::json,
                        CAST(:ts AS timestamptz), CAST(:ts AS timestamptz)
                    )
                    """
                ),
                {"ts": ts},
            )
            org_id = conn.execute(text("SELECT id FROM organizations LIMIT 1")).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO d13_replay_reservations (
                        id, created_at, updated_at, organization_id, institution_id,
                        exam_pack_code, exam_version_id, academic_year,
                        idempotency_key_hash, request_fingerprint, reservation_state,
                        owner_token, metadata_json
                    ) VALUES (
                        gen_random_uuid()::text, CAST(:ts AS timestamptz), CAST(:ts AS timestamptz),
                        :org, :org, 'pack', gen_random_uuid()::text, '2026',
                        repeat('a', 64), repeat('b', 64), 'reserved',
                        repeat('c', 64),
                        '{"d13_synthetic_test_only": true}'::json
                    )
                    """
                ),
                {"org": org_id, "ts": ts},
            )
        parsed = __import__("urllib.parse").urlparse(src_url)
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
                parsed.path.lstrip("/"),
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
                __import__("urllib.parse").urlparse(dst_url).path.lstrip("/"),
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
            org_count = conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar_one()
            replay_count = conn.execute(
                text("SELECT COUNT(*) FROM d13_replay_reservations")
            ).scalar_one()
            assert int(org_count) > 0
            assert int(replay_count) > 0
    finally:
        dump_path.unlink(missing_ok=True)
        drop_owned_pg_database(admin_url, src_name)
        drop_owned_pg_database(admin_url, dst_name)