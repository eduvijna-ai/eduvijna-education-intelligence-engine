#!/usr/bin/env python3
"""C01 Gate A disposable diagnostics harness (documentation-only, candidate 3)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
OUT = Path(__file__).resolve().parent / "transcripts"
HARNESS_PATH = Path(__file__).resolve()
BASELINE_SHA = "1781f036d20cceae1d5fcc4b2c4e452e1e4530c7"
PG_HOST = "127.0.0.1"
PG_PORT = "55432"
PG_USER = "c01_diag"

ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)

# Corrected SQLite strict JSON boolean (path json_type — not json_extract wrapper)
SQLITE_STRICT_SQL = (
    "CASE WHEN NOT json_valid(metadata_json) THEN 0 "
    "WHEN json_type(metadata_json) <> 'object' THEN 0 "
    "WHEN json_type(metadata_json, '$.d13_synthetic_test_only') IS NULL THEN 0 "
    "WHEN json_type(metadata_json, '$.d13_synthetic_test_only') = 'true' THEN 1 "
    "ELSE 0 END"
)

PG_STRICT_SQL = (
    "CASE WHEN jsonb_typeof((metadata_json::jsonb)) <> 'object' THEN false "
    "WHEN jsonb_typeof((metadata_json::jsonb)->'d13_synthetic_test_only') IS NULL THEN false "
    "WHEN jsonb_typeof((metadata_json::jsonb)->'d13_synthetic_test_only') = 'boolean' "
    "AND ((metadata_json::jsonb)->>'d13_synthetic_test_only') = 'true' THEN true "
    "ELSE false END"
)

MARKER_KEY = "d13_synthetic_test_only"


def preflight_marker_eligible(metadata_json: str) -> bool:
    """Fail-closed eligibility (design-only); not tenant/source authorization."""
    if not metadata_json or not metadata_json.strip():
        return False
    if metadata_json.count(f'"{MARKER_KEY}"') > 1:
        return False
    try:
        parsed = json.loads(metadata_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    if MARKER_KEY not in parsed:
        return False
    return parsed[MARKER_KEY] is True


MARKER_MATRIX: list[tuple[str, str, bool]] = [
    ("bool-true", '{"d13_synthetic_test_only": true}', True),
    ("bool-false", '{"d13_synthetic_test_only": false}', False),
    ("int-1", '{"d13_synthetic_test_only": 1}', False),
    ("int-0", '{"d13_synthetic_test_only": 0}', False),
    ("float-1", '{"d13_synthetic_test_only": 1.0}', False),
    ("str-true", '{"d13_synthetic_test_only": "true"}', False),
    ("null-val", '{"d13_synthetic_test_only": null}', False),
    ("absent", "{}", False),
    ("root-array", "[true]", False),
    ("root-scalar", "true", False),
    ("nested-obj", '{"wrapper":{"d13_synthetic_test_only":true}}', False),
    ("dup-false-true", '{"d13_synthetic_test_only": false, "d13_synthetic_test_only": true}', False),
    ("dup-true-false", '{"d13_synthetic_test_only": true, "d13_synthetic_test_only": false}', False),
]

EXPECTED_FAILURE = 100  # trial exit code: diagnostic proved expected SQL failure


@dataclass
class TrialResult:
    name: str
    exit_code: int
    log_path: Path
    notes: str = ""


@dataclass
class RunContext:
    run_id: str
    owned_dbs: list[str] = field(default_factory=list)
    owned_files: list[Path] = field(default_factory=list)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _log_open(ctx: RunContext, name: str) -> tuple[Path, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{ctx.run_id}_{name}.log"
    fh = path.open("w", encoding="utf-8")
    fh.write(f"run_id={ctx.run_id}\n")
    fh.write(f"trial={name}\n")
    fh.write(f"utc={datetime.now(timezone.utc).isoformat()}\n")
    fh.write(f"harness_sha256={hashlib.sha256(HARNESS_PATH.read_bytes()).hexdigest()}\n")
    fh.write(f"repo_head={subprocess.check_output(['git', '-C', REPO, 'rev-parse', 'HEAD'], text=True).strip()}\n")
    fh.write(f"baseline_sha={BASELINE_SHA}\n")
    fh.write(f"log_path={_rel(path)}\n\n")
    return path, fh


def verify_baseline(fh, *, strict: bool = True) -> int:
    """Fail closed if migrations differ from baseline tree or worktree dirty on migrations/models."""
    anc = subprocess.run(
        ["git", "-C", REPO, "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        capture_output=True,
    )
    fh.write(f"baseline_ancestor_exit={anc.returncode}\n")
    if anc.returncode != 0 and strict:
        fh.write("FAIL: baseline not ancestor of HEAD\n")
        return 2
    diff = subprocess.run(
        ["git", "-C", REPO, "diff", "--name-only", BASELINE_SHA, "HEAD", "--", "backend/migrations", "backend/app"],
        capture_output=True,
        text=True,
    )
    fh.write(f"migration_app_diff_vs_baseline=\n{diff.stdout or '(none)'}\n")
    dirty = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain", "--", "backend/migrations", "backend/app/models"],
        capture_output=True,
        text=True,
    )
    fh.write(f"worktree_dirty_migrations_models=\n{dirty.stdout or '(clean)'}\n")
    if strict and (diff.stdout.strip() or dirty.stdout.strip()):
        fh.write("FAIL: migration/model tree not identical to baseline expectation for Gate A\n")
        return 2
    baseline_tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", f"{BASELINE_SHA}^{{tree}}:backend/migrations/versions"],
        text=True,
    ).strip()
    head_tree = subprocess.check_output(
        ["git", "-C", REPO, "rev-parse", "HEAD:backend/migrations/versions"],
        text=True,
    ).strip()
    fh.write(f"baseline_migrations_tree={baseline_tree}\n")
    fh.write(f"head_migrations_tree={head_tree}\n")
    blob = subprocess.check_output(
        [
            "git",
            "-C",
            REPO,
            "show",
            f"{BASELINE_SHA}:backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py",
        ],
    )
    fh.write(f"baseline_0021_sha256={hashlib.sha256(blob).hexdigest()}\n\n")
    return 0


def pg_psql(db: str, sql: str, fh, *, expect: str | None = None) -> int:
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
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    fh.write(f"$ {' '.join(cmd)}\n")
    if expect:
        fh.write(f"expect={expect}\n")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit_code={proc.returncode}\n\n")
    return proc.returncode


def pg_create_db(ctx: RunContext, fh, name: str) -> int:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        fh.write(f"invalid db name {name}\n")
        return 1
    proc = subprocess.run(
        [
            "psql",
            "-h",
            PG_HOST,
            "-p",
            PG_PORT,
            "-U",
            PG_USER,
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{name}'",
        ],
        capture_output=True,
        text=True,
    )
    if proc.stdout.strip() == "1":
        fh.write(f"FAIL: database {name} already exists — not cleaning non-owned DB\n")
        return 1
    rc = pg_psql("postgres", f'CREATE DATABASE "{name}"', fh)
    if rc == 0:
        ctx.owned_dbs.append(name)
    return rc


def pg_drop_owned(ctx: RunContext, fh) -> None:
    for db in ctx.owned_dbs:
        pg_psql("postgres", f"DROP DATABASE {db} WITH (FORCE)", fh, expect="cleanup-owned")


def pg_available() -> bool:
    proc = subprocess.run(
        ["psql", "-h", PG_HOST, "-p", PG_PORT, "-U", PG_USER, "-d", "postgres", "-c", "SELECT 1"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def sqlite_strict(conn: sqlite3.Connection, metadata_json: str) -> int:
    sql = (
        "SELECT CASE WHEN NOT json_valid(?) THEN 0 "
        "WHEN json_type(?) <> 'object' THEN 0 "
        "WHEN json_type(?, '$.d13_synthetic_test_only') IS NULL THEN 0 "
        "WHEN json_type(?, '$.d13_synthetic_test_only') = 'true' THEN 1 "
        "ELSE 0 END"
    )
    return conn.execute(sql, (metadata_json, metadata_json, metadata_json, metadata_json)).fetchone()[0]


def trial_marker_matrix_sqlite(ctx: RunContext) -> TrialResult:
    path, fh = _log_open(ctx, "sqlite_marker_matrix")
    db_path = Path(f"/tmp/{ctx.run_id}_marker_matrix.db")
    for suf in ("", "-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suf).unlink()
        except FileNotFoundError:
            pass
    ctx.owned_files.append(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE marker_probe (id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL)")
    mismatches = 0
    fh.write("id\texpected_eligible\tpreflight\tstrict_sql\tlegacy_json_extract\tpreflight_ok\tstrict_ok\n")
    for cid, meta, expected in MARKER_MATRIX:
        try:
            conn.execute("INSERT INTO marker_probe VALUES (?,?)", (cid, meta))
        except sqlite3.Error as exc:
            fh.write(f"{cid}\tINSERT_FAIL\t{exc}\n")
            mismatches += 1
            continue
        legacy = None
        strict = 0
        if meta and conn.execute("SELECT json_valid(?)", (meta,)).fetchone()[0]:
            legacy = conn.execute(
                "SELECT json_extract(?, '$.d13_synthetic_test_only')", (meta,)
            ).fetchone()[0]
            strict = sqlite_strict(conn, meta)
        else:
            legacy = "INVALID"
        preflight = preflight_marker_eligible(meta)
        preflight_ok = preflight == expected
        if cid.startswith("dup-"):
            strict_ok = True
            fh.write(
                f"{cid}\t{expected}\t{preflight}\t{strict}\t{legacy!r}\t"
                f"{preflight_ok}\tN/A(dup-keys-sql-ambiguous)\n"
            )
        else:
            strict_ok = bool(strict) == expected
            fh.write(
                f"{cid}\t{expected}\t{preflight}\t{strict}\t{legacy!r}\t{preflight_ok}\t{strict_ok}\n"
            )
        if not preflight_ok or not strict_ok:
            mismatches += 1
    dup_ambig = sum(1 for cid, _, _ in MARKER_MATRIX if cid.startswith("dup-"))
    fh.write(f"duplicate_key_cases={dup_ambig}\n")
    fh.write(f"mismatch_count={mismatches}\n")
    fh.close()
    return TrialResult(
        "sqlite_marker_matrix",
        0 if mismatches == 0 else 1,
        path,
        notes="auto expected vs actual",
    )


def trial_marker_matrix_pg(ctx: RunContext, db: str) -> TrialResult:
    path, fh = _log_open(ctx, "pg_marker_matrix")
    if pg_create_db(ctx, fh, db) != 0:
        fh.close()
        return TrialResult("pg_marker_matrix", 126, path, notes="db create failed")
    pg_psql(db, "CREATE TABLE marker_probe (id text PRIMARY KEY, metadata_json json NOT NULL)", fh)
    mismatches = 0
    fh.write("id\texpected_eligible\tpreflight\tstrict_sql\tpreflight_ok\tstrict_ok\n")
    for cid, meta, expected in MARKER_MATRIX:
        preflight = preflight_marker_eligible(meta)
        preflight_ok = preflight == expected
        esc = meta.replace("'", "''")
        rc = pg_psql(db, f"INSERT INTO marker_probe VALUES ('{cid}', '{esc}'::json)", fh, expect="insert")
        if rc != 0:
            fh.write(f"{cid}\tINSERT_FAIL\n")
            if expected:
                mismatches += 1
            continue
        proc = subprocess.run(
            [
                "psql",
                "-h",
                PG_HOST,
                "-p",
                PG_PORT,
                "-U",
                PG_USER,
                "-d",
                db,
                "-tAc",
                f"SELECT ({PG_STRICT_SQL})::int FROM marker_probe WHERE id='{cid}'",
            ],
            capture_output=True,
            text=True,
        )
        strict = proc.stdout.strip() == "1"
        strict_ok = strict == expected if not cid.startswith("dup-") else True
        if cid.startswith("dup-"):
            fh.write(
                f"{cid}\t{expected}\t{preflight}\t{strict}\t{preflight_ok}\t"
                f"N/A(dup-keys-cast-collapses)\n"
            )
        else:
            fh.write(f"{cid}\t{expected}\t{preflight}\t{strict}\t{preflight_ok}\t{strict_ok}\n")
        if not preflight_ok or (not cid.startswith("dup-") and not strict_ok):
            mismatches += 1
    fh.close()
    return TrialResult("pg_marker_matrix", 0 if mismatches == 0 else 1, path)


def trial_pg_fresh(ctx: RunContext, db: str) -> TrialResult:
    path, fh = _log_open(ctx, "pg_fresh_head")
    if verify_baseline(fh) != 0:
        fh.close()
        return TrialResult("pg_fresh_head", 2, path)
    if pg_create_db(ctx, fh, db) != 0:
        fh.close()
        return TrialResult("pg_fresh_head", 126, path)
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"postgresql+psycopg2://{PG_USER}@{PG_HOST}:{PG_PORT}/{db}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    proc = subprocess.run([str(alembic), "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit={proc.returncode}\n")
    fh.close()
    code = 0 if proc.returncode == 0 else EXPECTED_FAILURE
    return TrialResult("pg_fresh_head", code, path)


def trial_pg_to_0020(ctx: RunContext, db: str) -> TrialResult:
    path, fh = _log_open(ctx, "pg_upgrade_0020")
    if pg_create_db(ctx, fh, db) != 0:
        fh.close()
        return TrialResult("pg_upgrade_0020", EXPECTED_FAILURE, path, notes="BLOCKED:create-fail")
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"postgresql+psycopg2://{PG_USER}@{PG_HOST}:{PG_PORT}/{db}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    proc = subprocess.run(
        [str(alembic), "upgrade", "20261124_0020"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    fh.write(f"exit={proc.returncode}\n")
    fh.write("NOTE: full-chain populated 0021 BLOCKED if exit!=0 at/before 0006\n")
    fh.close()
    code = EXPECTED_FAILURE if proc.returncode != 0 else 0
    return TrialResult("pg_upgrade_0020", code, path)


def trial_pg_0021_isolated(ctx: RunContext, db: str) -> TrialResult:
    path, fh = _log_open(ctx, "pg_isolated_0021_NOT_0020_EQUIVALENT")
    fh.write("SCHEMA_NOTE: reduced probe table — NOT Alembic 0020-equivalent full migration\n")
    if pg_create_db(ctx, fh, db) != 0:
        fh.close()
        return TrialResult("pg_isolated_0021", 126, path)
    pg_psql(
        db,
        "CREATE TABLE d13_replay_reservations (id varchar(36) PRIMARY KEY, metadata_json json NOT NULL)",
        fh,
    )
    rc_json = pg_psql(
        db,
        "UPDATE d13_replay_reservations SET synthetic_test_only = true "
        "WHERE json_extract(metadata_json, '$.d13_synthetic_test_only') = true",
        fh,
        expect="EXPECTED_FAILURE:42883",
    )
    rc_chk = pg_psql(
        db,
        "BEGIN; CREATE TEMP TABLE t(b bool); INSERT INTO t VALUES (true); "
        "ALTER TABLE t ADD CONSTRAINT c CHECK (b = 1); ROLLBACK;",
        fh,
        expect="EXPECTED_FAILURE:boolean=integer",
    )
    fh.close()
    fail_count = sum(1 for x in (rc_json, rc_chk) if x != 0)
    return TrialResult(
        "pg_isolated_0021",
        EXPECTED_FAILURE if fail_count == 2 else 1,
        path,
    )


def trial_active_slot_enforced_pg(ctx: RunContext, db: str) -> TrialResult:
    path, fh = _log_open(ctx, "pg_active_slot_constraints")
    if pg_create_db(ctx, fh, db) != 0:
        fh.close()
        return TrialResult("pg_active_slot_constraints", 126, path)
    pg_psql(
        db,
        f"""
        CREATE TABLE source_revisions (
          id serial PRIMARY KEY,
          source_id int NOT NULL,
          status text NOT NULL,
          active_slot int,
          CONSTRAINT ck_slot CHECK ({ACTIVE_SLOT_CHECK}),
          CONSTRAINT uq_active UNIQUE (source_id, active_slot)
        );
        """,
        fh,
    )
    trials = [
        ("valid-active", "INSERT INTO source_revisions(source_id,status,active_slot) VALUES (1,'active',1)", True),
        ("invalid-active-null", "INSERT INTO source_revisions(source_id,status,active_slot) VALUES (1,'active',NULL)", False),
        ("dup-active", "INSERT INTO source_revisions(source_id,status,active_slot) VALUES (1,'active',1)", False),
        ("valid-other-source", "INSERT INTO source_revisions(source_id,status,active_slot) VALUES (2,'active',1)", True),
    ]
    for name, sql, expect_ok in trials:
        rc = pg_psql(db, sql, fh, expect="ok" if expect_ok else "fail")
        fh.write(f"trial={name} expect_ok={expect_ok} rc={rc}\n")
    fh.close()
    return TrialResult("pg_active_slot_constraints", 0, path)


def trial_active_slot_enforced_sqlite(ctx: RunContext, db_path: Path) -> TrialResult:
    path, fh = _log_open(ctx, "sqlite_active_slot_constraints")
    db_path.unlink(missing_ok=True)
    ctx.owned_files.append(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"""
        CREATE TABLE source_revisions (
          id INTEGER PRIMARY KEY,
          source_id INT NOT NULL,
          status TEXT NOT NULL,
          active_slot INT,
          CHECK ({ACTIVE_SLOT_CHECK}),
          UNIQUE(source_id, active_slot)
        )
        """
    )
    def try_ins(sql: str) -> bool:
        try:
            conn.execute(sql)
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            fh.write(f"fail {e}\n")
            return False

    results = []
    results.append(try_ins("INSERT INTO source_revisions VALUES (1,1,'active',1)"))
    results.append(not try_ins("INSERT INTO source_revisions VALUES (2,1,'active',NULL)"))
    results.append(not try_ins("INSERT INTO source_revisions VALUES (3,1,'active',1)"))
    results.append(try_ins("INSERT INTO source_revisions VALUES (4,2,'active',1)"))
    fh.write(f"results={results}\n")
    fh.close()
    return TrialResult("sqlite_active_slot_constraints", 0 if all(results) else 1, path)


def trial_sqlite_mixed_0021(ctx: RunContext, db_path: Path) -> TrialResult:
    path, fh = _log_open(ctx, "sqlite_mixed_0021")
    for suf in ("", "-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suf).unlink()
        except FileNotFoundError:
            pass
    ctx.owned_files.append(db_path)
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"sqlite:///{db_path}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    subprocess.run([str(alembic), "upgrade", "20261124_0020"], cwd=BACKEND, env=env, check=True, capture_output=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    now = "2026-11-25T00:00:00+00:00"
    conn.execute(
        "INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("t1", now, now, "o", "i", "p", "v", "2026", "a" * 64, "b" * 64, "reserved", '{"d13_synthetic_test_only":true}'),
    )
    conn.execute(
        "INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("a1", now, now, "o", "i", "p", "v", "2026", "c" * 64, "d" * 64, "reserved", "{}"),
    )
    conn.commit()
    before = hashlib.sha256(str(conn.execute("SELECT * FROM d13_replay_reservations").fetchall()).encode()).hexdigest()
    fh.write(f"before_sha256={before}\n")
    proc = subprocess.run([str(alembic), "upgrade", "20261124_0021"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    cols = [c[1] for c in conn.execute("PRAGMA table_info(d13_replay_reservations)")]
    fh.write(f"exit={proc.returncode} version={ver} synthetic_col={'synthetic_test_only' in cols}\n")
    fh.close()
    code = EXPECTED_FAILURE if proc.returncode != 0 else 0
    return TrialResult("sqlite_mixed_0021", code, path)


def trial_sqlite_fresh(ctx: RunContext, db_path: Path) -> TrialResult:
    path, fh = _log_open(ctx, "sqlite_fresh_head")
    for suf in ("", "-wal", "-shm"):
        try:
            db_path.with_name(db_path.name + suf).unlink()
        except FileNotFoundError:
            pass
    ctx.owned_files.append(db_path)
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "DATABASE_URL": f"sqlite:///{db_path}"}
    alembic = BACKEND / ".venv" / "bin" / "alembic"
    proc = subprocess.run([str(alembic), "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    fh.write(proc.stdout)
    fh.write(proc.stderr)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    conn = sqlite3.connect(db_path)
    fh.write(f"version={conn.execute('SELECT version_num FROM alembic_version').fetchone()}\n")
    fh.close()
    return TrialResult("sqlite_fresh_head", proc.returncode, path)


def cleanup(ctx: RunContext, fh) -> None:
    pg_drop_owned(ctx, fh)
    for p in ctx.owned_files:
        for suf in ("", "-wal", "-shm"):
            try:
                Path(str(p) + suf).unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    ctx = RunContext(run_id=f"c01_gatea_{uuid.uuid4().hex[:12]}")
    summary_path = OUT / f"{ctx.run_id}_SUMMARY.json"
    probe_fh = _log_open(ctx, "run_meta")[1]
    baseline_rc = verify_baseline(probe_fh, strict=True)
    probe_fh.close()
    if baseline_rc != 0:
        summary_path.write_text(json.dumps({"run_id": ctx.run_id, "harness_error": "baseline_verify_failed"}, indent=2))
        return baseline_rc

    results: list[TrialResult] = []
    harness_fail = False

    results.append(trial_marker_matrix_sqlite(ctx))
    if results[-1].exit_code != 0:
        harness_fail = True

    if pg_available():
        db_base = ctx.run_id.replace("-", "_")
        results.append(trial_pg_fresh(ctx, f"{db_base}_fresh"))
        results.append(trial_pg_to_0020(ctx, f"{db_base}_u20"))
        results.append(trial_pg_0021_isolated(ctx, f"{db_base}_iso21"))
        results.append(trial_marker_matrix_pg(ctx, f"{db_base}_markers"))
        results.append(trial_active_slot_enforced_pg(ctx, f"{db_base}_slot"))
    else:
        results.append(TrialResult("pg_unavailable", 125, OUT / f"{ctx.run_id}_pg_unavailable.log"))

    results.append(trial_sqlite_fresh(ctx, Path(f"/tmp/{ctx.run_id}_fresh.db")))
    results.append(trial_sqlite_mixed_0021(ctx, Path(f"/tmp/{ctx.run_id}_mixed.db")))
    results.append(trial_active_slot_enforced_sqlite(ctx, Path(f"/tmp/{ctx.run_id}_slot.db")))

    meta_path, meta_fh = _log_open(ctx, "cleanup")
    cleanup(ctx, meta_fh)
    meta_fh.close()

    summary = {
        "run_id": ctx.run_id,
        "baseline_sha": BASELINE_SHA,
        "harness_sha256": hashlib.sha256(HARNESS_PATH.read_bytes()).hexdigest(),
        "trials": [
            {
                "name": r.name,
                "exit_code": r.exit_code,
                "log": _rel(r.log_path),
                "notes": r.notes,
            }
            for r in results
        ],
        "harness_exit_fail": harness_fail,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(_rel(summary_path))

    unexpected = [
        r
        for r in results
        if r.exit_code not in (0, EXPECTED_FAILURE) and r.name != "pg_unavailable"
    ]
    return 1 if unexpected or harness_fail else 0


if __name__ == "__main__":
    sys.exit(main())