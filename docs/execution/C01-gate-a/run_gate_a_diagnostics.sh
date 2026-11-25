#!/usr/bin/env bash
# C01 Gate A — disposable migration diagnostics only.
# ALLOWLIST: localhost PostgreSQL on port 55432, SQLite files under /tmp/c01_sqlite_*
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BACKEND="$REPO_ROOT/backend"
OUT_DIR="$(dirname "$0")"
LOG="$OUT_DIR/C01-DIAGNOSTIC-RUN.log"
BASELINE_SHA="1781f036d20cceae1d5fcc4b2c4e452e1e4530c7"
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
PG_URL="postgresql+psycopg2://c01_diag@127.0.0.1:55432/c01_alembic_disposable"
export PYTHONPATH="$BACKEND"
ALEMBIC="$BACKEND/.venv/bin/alembic"
cd "$BACKEND"

{
  echo "=== C01 Gate A diagnostic run ==="
  echo "baseline_sha=$BASELINE_SHA head_sha=$HEAD_SHA"
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "pg_url_sanitized=postgresql+psycopg2://c01_diag@127.0.0.1:55432/c01_alembic_disposable"
  echo "pg_version=$(psql -h 127.0.0.1 -p 55432 -U c01_diag -d postgres -tAc 'SHOW server_version;' 2>/dev/null || echo UNAVAILABLE)"
  echo

  echo "--- PG: drop/recreate disposable database ---"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d postgres -c "DROP DATABASE IF EXISTS c01_alembic_disposable;" || true
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d postgres -c "CREATE DATABASE c01_alembic_disposable;"

  echo "--- PG: alembic upgrade head (fresh) ---"
  set +e
  DATABASE_URL="$PG_URL" "$ALEMBIC" upgrade head 2>&1
  PG_HEAD_EC=$?
  set -e
  echo "exit_code=$PG_HEAD_EC"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable -c "SELECT version_num FROM alembic_version;" 2>&1 || true
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable -c "\d d13_replay_reservations" 2>&1 || true

  echo "--- PG: fresh to 0020 then synthetic seed then 0021 ---"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d postgres -c "DROP DATABASE IF EXISTS c01_alembic_disposable;"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d postgres -c "CREATE DATABASE c01_alembic_disposable;"
  DATABASE_URL="$PG_URL" "$ALEMBIC" upgrade 20261124_0020 2>&1
  NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable <<'SQL'
INSERT INTO d13_replay_reservations (
  id, created_at, updated_at, organization_id, institution_id,
  exam_pack_code, exam_version_id, academic_year,
  idempotency_key_hash, request_fingerprint, reservation_state, metadata_json
) VALUES
(
  'c01-synth-valid-0001', '$NOW'::timestamptz, '$NOW'::timestamptz,
  'org-synth', 'inst-synth', 'PACK-SYNTH', 'ver-synth-0001', '2026',
  repeat('a', 64), repeat('b', 64), 'reserved',
  '{"d13_synthetic_test_only": true}'::jsonb
),
(
  'c01-synth-invalid-01', '$NOW'::timestamptz, '$NOW'::timestamptz,
  'org-synth', 'inst-synth', 'PACK-SYNTH', 'ver-synth-0001', '2026',
  repeat('c', 64), repeat('d', 64), 'reserved',
  '{"d13_synthetic_test_only": 1}'::jsonb
);
SQL
  # shell expands NOW in heredoc via envsubst substitute
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable -v NOW="$NOW" -c "
INSERT INTO d13_replay_reservations (
  id, created_at, updated_at, organization_id, institution_id,
  exam_pack_code, exam_version_id, academic_year,
  idempotency_key_hash, request_fingerprint, reservation_state, metadata_json
) VALUES
(
  'c01-synth-valid-0001', :'NOW'::timestamptz, :'NOW'::timestamptz,
  'org-synth', 'inst-synth', 'PACK-SYNTH', 'ver-synth-0001', '2026',
  repeat('a', 64), repeat('b', 64), 'reserved',
  '{\"d13_synthetic_test_only\": true}'::jsonb
),
(
  'c01-synth-int-one-01', :'NOW'::timestamptz, :'NOW'::timestamptz,
  'org-synth', 'inst-synth', 'PACK-SYNTH', 'ver-synth-0001', '2026',
  repeat('c', 64), repeat('d', 64), 'reserved',
  '{\"d13_synthetic_test_only\": 1}'::jsonb
);" 2>&1 || true

  set +e
  DATABASE_URL="$PG_URL" "$ALEMBIC" upgrade 20261124_0021 2>&1
  PG_21_EC=$?
  set -e
  echo "exit_code_0021=$PG_21_EC"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable -c "SELECT version_num FROM alembic_version;" 2>&1 || true
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable -c "SELECT column_name FROM information_schema.columns WHERE table_name='d13_replay_reservations' AND column_name='synthetic_test_only';" 2>&1 || true

  echo "--- PG: isolated boolean/check constraint probe (no migration edit) ---"
  psql -h 127.0.0.1 -p 55432 -U c01_diag -d c01_alembic_disposable <<'SQL'
BEGIN;
CREATE TABLE IF NOT EXISTS c01_bool_probe (id int, flag boolean NOT NULL DEFAULT false);
UPDATE c01_bool_probe SET flag = 1 WHERE id = 1;
ALTER TABLE c01_bool_probe ADD CONSTRAINT ck_c01_bool_probe CHECK (flag = 1);
ROLLBACK;
SQL

  echo "--- SQLite: fresh upgrade head ---"
  SQLITE_FRESH="/tmp/c01_sqlite_fresh_$$.db"
  rm -f "$SQLITE_FRESH" "${SQLITE_FRESH}-wal" "${SQLITE_FRESH}-shm"
  set +e
  DATABASE_URL="sqlite:///$SQLITE_FRESH" "$ALEMBIC" upgrade head 2>&1
  SQLITE_HEAD_EC=$?
  set -e
  echo "exit_code=$SQLITE_HEAD_EC"
  sqlite3 "$SQLITE_FRESH" "PRAGMA foreign_keys=ON; SELECT version_num FROM alembic_version;" 2>&1
  sqlite3 "$SQLITE_FRESH" "PRAGMA table_info(d13_replay_reservations);" 2>&1 | grep synthetic || true

  echo "--- SQLite: populated 0020->0021 with marker cases ---"
  SQLITE_POP="/tmp/c01_sqlite_pop_$$.db"
  rm -f "$SQLITE_POP" "${SQLITE_POP}-wal" "${SQLITE_POP}-shm"
  DATABASE_URL="sqlite:///$SQLITE_POP" "$ALEMBIC" upgrade 20261124_0020
  sqlite3 "$SQLITE_POP" "PRAGMA foreign_keys=ON;
INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json)
VALUES ('s1','2026-11-25 00:00:00','2026-11-25 00:00:00','o','i','p','v','2026',printf('%064d',0),printf('%064d',1),'reserved','{\"d13_synthetic_test_only\":true}'),
('s2','2026-11-25 00:00:00','2026-11-25 00:00:00','o','i','p','v','2026',printf('%064d',2),printf('%064d',3),'reserved','{\"d13_synthetic_test_only\":1}');
SELECT id, json_extract(metadata_json,'$.d13_synthetic_test_only') AS extracted FROM d13_replay_reservations;"
  set +e
  DATABASE_URL="sqlite:///$SQLITE_POP" "$ALEMBIC" upgrade 20261124_0021 2>&1
  SQLITE_21_EC=$?
  set -e
  echo "exit_code_0021=$SQLITE_21_EC"
  sqlite3 "$SQLITE_POP" "SELECT version_num FROM alembic_version; SELECT id, synthetic_test_only, metadata_json FROM d13_replay_reservations;" 2>&1

  echo "--- SQLite: WAL restart after attempted 0021 on failed DB ---"
  SQLITE_FAIL="/tmp/c01_sqlite_fail_$$.db"
  rm -f "$SQLITE_FAIL"*
  DATABASE_URL="sqlite:///$SQLITE_FAIL" "$ALEMBIC" upgrade 20261124_0020 || true
  # force a failing 0021 by inserting row that would fail check after backfill ambiguity — use empty metadata
  sqlite3 "$SQLITE_FAIL" "INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json)
VALUES ('bad','2026-11-25 00:00:00','2026-11-25 00:00:00','o','i','p','v','2026',printf('%064d',4),printf('%064d',5),'replayed',json_object('d13_synthetic_test_only',json('true')),'x','1.0',json('{}'),'sha',null);" 2>&1 || sqlite3 "$SQLITE_FAIL" "INSERT INTO d13_replay_reservations (id, created_at, updated_at, organization_id, institution_id, exam_pack_code, exam_version_id, academic_year, idempotency_key_hash, request_fingerprint, reservation_state, metadata_json, owner_token, payload_sha256, result_snapshot_version, result_json)
VALUES ('bad','2026-11-25 00:00:00','2026-11-25 00:00:00','o','i','p','v','2026',printf('%064d',4),printf('%064d',5),'replayed',json_object('d13_synthetic_test_only',json('true')),'tok','sha','1.0',json('{}'));" 2>&1
  set +e
  DATABASE_URL="sqlite:///$SQLITE_FAIL" "$ALEMBIC" upgrade 20261124_0021 2>&1
  set -e
  sqlite3 "$SQLITE_FAIL" "SELECT version_num FROM alembic_version; PRAGMA table_info(d13_replay_reservations);" 2>&1

  echo "=== end diagnostic run ==="
} | tee "$LOG"