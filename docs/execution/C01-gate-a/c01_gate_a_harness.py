#!/usr/bin/env python3
"""C01 Gate A disposable diagnostics harness (documentation-only).

ALLOWLIST: PostgreSQL 127.0.0.1:55432 owned DB name prefix c01_gatea_;
SQLite files under /tmp/c01_gatea_* owned by this run id only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
OUT = Path(__file__).resolve().parent / "transcripts"
BASELINE_SHA = "1781f036d20cceae1d5fcc4b2c4e452e1e4530c7"
FROZEN_MIGRATION_TREE = BACKEND / "migrations" / "versions"
PG_HOST = "127.0.0.1"
PG_PORT = "55432"
PG_USER = "c01_diag"

# Portable INTEGER active_slot invariant (proposed Gate B — NOT applied)
ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)

# Strict JSON boolean marker predicates (design probes only)
PG_STRICT_MARKER = (
    "jsonb_typeof((metadata_json::jsonb)->'d13_synthetic_test_only') = 'boolean' "
    "AND (metadata_json::jsonb)->>'d13_synthetic_test_only' = 'true'"
)

SQLITE_STRICT_MARKER = (
    "json_valid(metadata_json) "
    "AND json_type(metadata_json) = 'object' "
    "AND json_type(json_extract(metadata_json, '$.d13_synthetic_test_only')) = 'true'"
)


@dataclass
class TrialResult:
    name: str
    exit_code: int
    log_path: Path


def _run_id() -> str:
    return f"c01_gatea_{uuid.uuid4().hex[:12]}"


def _log_open(run_id: str, name: str) -> tuple[Path, object]:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{run_id}_{name}.log"
    fh = path.open("w", encoding="utf-8")
    fh.write(f"run_id={run_id}\n")
    fh.write(f"trial={name}\n")
    fh.write(f"utc={datetime.now(timezone.utc).isoformat()}\n")
    fh.write(f"repo_head={subprocess.check_output(['git', '-C', REPO, 'rev-parse', 'HEAD'], text=True).strip()}\n")
    fh.write(f"expected_baseline_ancestry={BASELINE_SHA}\n\n")
    return path, fh


def verify_baseline(fh) -> None:
    merged = subprocess.run(
        ["git", "-C", REPO, "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        capture_output=True,
    )
    fh.write(f"baseline_ancestor_check exit={merged.returncode}\n")
    tree = subprocess.check_output(["git", "-C", REPO, "rev-parse", f"{BASELINE_SHA}^{{tree}}"], text=True).strip()
    local = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD:backend/migrations/versions"], text=True).strip()
    fh.write(f"baseline_migrations_tree={tree}\n")
    fh.write(f"head_migrations_tree={local}\n")
    if not list(FROZEN_MIGRATION_TREE.glob("*.py")):
        raise RuntimeError("migration tree missing")
    sample = (FROZEN_MIGRATION_TREE / "20261124_0021_d13_replay_synthetic_flag.py").read_bytes()
    fh.write(f"sample_0021_sha256={hashlib.sha256(sample).hexdigest()}\n\n")


def pg_psql(db: str, sql: str, fh, *, on_error_stop: bool = True) -> int:
    cmd = [
        "psql",
        "-h",
        PG_HOST,
        "-p",
        PG_PORT,
        "-U",
        PG_USER,
        "-d",
        db,
        "-v",
        "ON_ERROR_STOP=1" if on_error_stop else "ON_ERROR_STOP=0",
        "-c",
        sql,
    ]
    fh.write(f"$ {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"\nexit_code={proc.returncode}\n\n")
    return proc.returncode


def pg_available(fh) -> bool:
    rc = pg_psql("postgres", "SELECT version();", fh, on_error_stop=False)
    return rc == 0


def trial_pg_fresh_head(run_id: str, db: str) -> TrialResult:
    path, fh = _log_open(run_id, "pg_fresh_head")
    verify_baseline(fh)
    if not pg_available(fh):
        fh.write("PG_UNAVAILABLE\n")
        fh.close()
        return TrialResult("pg_fresh_head", 127, path)
    pg_psql("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE);", fh, on_error_stop=False)
    pg_psql("postgres", f"CREATE DATABASE {db};", fh, on_error_stop=False)
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"postgresql+psycopg2://{PG_USER}@{PG_HOST}:{PG_PORT}/{db}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    if not alembic.is_file():
        fh.write("ALEMBIC_VENV_MISSING\n")
        fh.close()
        return TrialResult("pg_fresh_head", 126, path)
    proc = subprocess.run([str(alembic), "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write("=== alembic upgrade head (raw) ===\n")
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit_code={proc.returncode}\n")
    pg_psql(db, "SELECT version_num FROM alembic_version;", fh, on_error_stop=False)
    fh.close()
    pg_psql("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE);", Path(path).open("a"), on_error_stop=False)
    return TrialResult("pg_fresh_head", proc.returncode, path)


def trial_pg_isolated_0021(run_id: str, db: str) -> TrialResult:
    path, fh = _log_open(run_id, "pg_isolated_0021")
    pg_psql("postgres", f"CREATE DATABASE {db};", fh, on_error_stop=False)
    ddl = textwrap.dedent(
        """
        DROP TABLE IF EXISTS d13_replay_reservations CASCADE;
        CREATE TABLE d13_replay_reservations (
          id varchar(36) PRIMARY KEY,
          metadata_json json NOT NULL
        );
        INSERT INTO d13_replay_reservations VALUES
          ('m-bool', '{"d13_synthetic_test_only": true}'::json),
          ('m-int', '{"d13_synthetic_test_only": 1}'::json),
          ('m-str', '{"d13_synthetic_test_only": "true"}'::json);
        ALTER TABLE d13_replay_reservations ADD COLUMN synthetic_test_only boolean NOT NULL DEFAULT false;
        """
    )
    for stmt in filter(None, ddl.strip().split(";")):
        pg_psql(db, stmt.strip() + ";", fh)
    fh.write("=== strict marker probe (proposed) ===\n")
    pg_psql(db, f"SELECT id, ({PG_STRICT_MARKER}) AS strict_eligible FROM d13_replay_reservations ORDER BY id;", fh, on_error_stop=False)
    fh.write("=== migration-source json_extract (expect 42883) ===\n")
    pg_psql(
        db,
        "UPDATE d13_replay_reservations SET synthetic_test_only = true "
        "WHERE json_extract(metadata_json, '$.d13_synthetic_test_only') = true;",
        fh,
        on_error_stop=False,
    )
    fh.write("=== CHECK (synthetic_test_only = 1) on boolean column (expect 42804) ===\n")
    pg_psql(
        db,
        "BEGIN; UPDATE d13_replay_reservations SET synthetic_test_only = true "
        "WHERE id = 'm-bool'; ALTER TABLE d13_replay_reservations "
        "ADD CONSTRAINT ck_probe CHECK (synthetic_test_only = 1); ROLLBACK;",
        fh,
        on_error_stop=False,
    )
    fh.write("=== CHECK (synthetic_test_only IS TRUE) probe ===\n")
    pg_psql(
        db,
        "BEGIN; ALTER TABLE d13_replay_reservations "
        "ADD CONSTRAINT ck_probe_is_true CHECK (synthetic_test_only IS TRUE); ROLLBACK;",
        fh,
        on_error_stop=False,
    )
    fh.close()
    pg_psql("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE);", Path(path).open("a"), on_error_stop=False)
    return TrialResult("pg_isolated_0021", 0, path)


def trial_active_slot_probe(run_id: str, db: str) -> TrialResult:
    path, fh = _log_open(run_id, "active_slot_check_probe")
    pg_psql("postgres", f"CREATE DATABASE {db};", fh, on_error_stop=False)
    pg_psql(
        db,
        "CREATE TABLE c01_active_slot_probe (id int, status text, active_slot int);",
        fh,
    )
    cases = [
        (1, "active", 1),
        (2, "active", None),
        (3, "active", 2),
        (4, "retired", None),
        (5, "retired", 1),
    ]
    for cid, status, slot in cases:
        val = "NULL" if slot is None else str(slot)
        pg_psql(db, f"INSERT INTO c01_active_slot_probe VALUES ({cid}, '{status}', {val});", fh, on_error_stop=False)
    fh.write(f"=== proposed check: {ACTIVE_SLOT_CHECK} ===\n")
    pg_psql(
        db,
        f"SELECT id, status, active_slot, ({ACTIVE_SLOT_CHECK}) AS ok FROM c01_active_slot_probe ORDER BY id;",
        fh,
        on_error_stop=False,
    )
    fh.write("=== invalid current migration check (IS 1) on integer ===\n")
    pg_psql(
        db,
        "SELECT id, ((status = 'active' AND active_slot IS 1) OR (status <> 'active' AND active_slot IS NULL)) AS ok FROM c01_active_slot_probe ORDER BY id;",
        fh,
        on_error_stop=False,
    )
    fh.close()
    pg_psql("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE);", Path(path).open("a"), on_error_stop=False)
    return TrialResult("active_slot_check_probe_pg", 0, path)


def trial_sqlite_markers(run_id: str, db_path: Path) -> TrialResult:
    path, fh = _log_open(run_id, "sqlite_marker_probes")
    for suffix in ("", "-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suffix).unlink()
        except FileNotFoundError:
            pass
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"sqlite:///{db_path}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    subprocess.run([str(alembic), "upgrade", "20261124_0020"], cwd=BACKEND, env=env, check=True, capture_output=True, text=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    now = "2026-11-25T00:00:00+00:00"
    rows = [
        ("json-true", '{"d13_synthetic_test_only": true}', "0" * 64, "1" * 64),
        ("json-int1", '{"d13_synthetic_test_only": 1}', "2" * 64, "3" * 64),
        ("json-str", '{"d13_synthetic_test_only": "true"}', "4" * 64, "5" * 64),
        ("json-absent", "{}", "6" * 64, "7" * 64),
        ("json-malformed", "not-json", "8" * 64, "9" * 64),
    ]
    for cid, meta, kh, fp in rows:
        try:
            conn.execute(
                "INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, now, now, "o", "i", "p", "v", "2026", kh, fp, "reserved", meta),
            )
        except sqlite3.Error as exc:
            fh.write(f"insert_fail {cid}: {exc}\n")
    conn.commit()
    fh.write("--- legacy json_extract vs strict (per-row) ---\n")
    for cid, meta in conn.execute("SELECT id, metadata_json FROM d13_replay_reservations ORDER BY id"):
        legacy = None
        strict = None
        if not conn.execute("SELECT json_valid(?)", (meta,)).fetchone()[0]:
            fh.write(f"({cid}, legacy=INVALID_JSON, strict=0)\n")
            continue
        legacy = conn.execute(
            "SELECT json_extract(?, '$.d13_synthetic_test_only')", (meta,)
        ).fetchone()[0]
        strict = conn.execute(
            "SELECT json_type(json_extract(?, '$.d13_synthetic_test_only')) = 'true'",
            (meta,),
        ).fetchone()[0]
        fh.write(f"({cid}, legacy={legacy!r}, strict_json_type_true={strict})\n")
    proc = subprocess.run([str(alembic), "upgrade", "20261124_0021"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write("=== alembic 0021 raw ===\n")
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit={proc.returncode}\n")
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    cols = [c[1] for c in conn.execute("PRAGMA table_info(d13_replay_reservations)")]
    fh.write(f"version={ver} has_synthetic_col={'synthetic_test_only' in cols}\n")
    fh.close()
    return TrialResult("sqlite_marker_probes", proc.returncode, path)


def trial_sqlite_fresh(run_id: str, db_path: Path) -> TrialResult:
    path, fh = _log_open(run_id, "sqlite_fresh_head")
    for suffix in ("", "-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suffix).unlink()
        except FileNotFoundError:
            pass
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"sqlite:///{db_path}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    proc = subprocess.run([str(alembic), "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit={proc.returncode}\n")
    conn = sqlite3.connect(db_path)
    fh.write(f"version={conn.execute('SELECT version_num FROM alembic_version').fetchone()}\n")
    fh.close()
    return TrialResult("sqlite_fresh_head", proc.returncode, path)


def trial_sqlite_active_slot(run_id: str, db_path: Path) -> TrialResult:
    path, fh = _log_open(run_id, "sqlite_active_slot_probe")
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE c01_active_slot_probe (id INT, status TEXT, active_slot INT)")
    cases = [(1, "active", 1), (2, "active", None), (3, "active", 2), (4, "retired", None), (5, "retired", 1)]
    for cid, status, slot in cases:
        conn.execute("INSERT INTO c01_active_slot_probe VALUES (?,?,?)", (cid, status, slot))
    fh.write(f"proposed: {ACTIVE_SLOT_CHECK}\n")
    for row in conn.execute(
        f"SELECT id, status, active_slot, ({ACTIVE_SLOT_CHECK}) FROM c01_active_slot_probe ORDER BY id"
    ):
        fh.write(f"{row}\n")
    for row in conn.execute(
        "SELECT id, ((status = 'active' AND active_slot IS 1) OR (status <> 'active' AND active_slot IS NULL)) FROM c01_active_slot_probe ORDER BY id"
    ):
        fh.write(f"legacy_is1 {row}\n")
    fh.close()
    return TrialResult("sqlite_active_slot_probe", 0, path)


def main() -> int:
    run_id = _run_id()
    summary_path = OUT / f"{run_id}_SUMMARY.json"
    OUT.mkdir(parents=True, exist_ok=True)
    pg_db = f"{run_id}_pg"
    results: list[TrialResult] = []
    if pg_available(_log_open(run_id, "pg_ping")[1]):
        results.extend(
            [
                trial_pg_fresh_head(run_id, pg_db),
                trial_pg_isolated_0021(run_id, f"{pg_db}_iso"),
                trial_active_slot_probe(run_id, f"{pg_db}_slot"),
            ]
        )
    else:
        results.append(TrialResult("pg_unavailable", 125, OUT / f"{run_id}_pg_unavailable.log"))
    sqlite_base = Path(f"/tmp/{run_id}")
    results.append(trial_sqlite_fresh(run_id, sqlite_base.with_name(f"{sqlite_base.name}_fresh.db")))
    results.append(trial_sqlite_markers(run_id, sqlite_base.with_name(f"{sqlite_base.name}_markers.db")))
    results.append(trial_sqlite_active_slot(run_id, sqlite_base.with_name(f"{sqlite_base.name}_slot.db")))
    for p in sqlite_base.parent.glob(f"{run_id}*"):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "baseline_sha": BASELINE_SHA,
                "trials": [{"name": r.name, "exit_code": r.exit_code, "log": str(r.log_path)} for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())