# C01 Gate A diagnostics

**Diagnostic baseline code:** develop `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7` (migrations unmodified)  
**Runner:** Cursor Cloud Agent disposable VM, 2026-11-25  
**PostgreSQL:** 16.15 (Ubuntu packages), `127.0.0.1:55432`, DB `c01_alembic_disposable`, role `c01_diag` (trust, localhost only)  
**SQLite:** file-backed under `/tmp/c01_sqlite_*.db`  
**No production access; synthetic fixture IDs only**

## Reproduction matrix

| Trial | Dialect | Path | Result | `alembic_version` after | Evidence file |
| --- | --- | --- | --- | --- | --- |
| Fresh empty → head | SQLite | Alembic full chain | **PASS** | `20261124_0021` | `/tmp/c01_sqlite_fresh.db` (ephemeral) |
| Fresh empty → head | PostgreSQL | Alembic full chain | **FAIL** | *(no table — rolled back)* | `C01-gate-a/pg_fresh_upgrade_head.log` |
| Populated 0020 → 0021 mixed markers | SQLite | Alembic | **FAIL** | `20261124_0020` | `C01-gate-a/sqlite_marker_matrix.log` |
| Populated true + absent rows | SQLite | Alembic | **FAIL** | `20261124_0020`, no `synthetic_test_only` col | Gate A Python trial (log inline below) |
| WAL mode 0020→0021 single true row | SQLite | Alembic | **PASS** | `20261124_0021` | ephemeral |
| Isolated 0021 SQL on 0020-shaped table | PostgreSQL | Manual DDL replay | **FAIL** | N/A | `C01-gate-a/pg_isolated_0021_steps.log` |

## PostgreSQL fresh-chain failure (pre-0021)

First blocking error on disposable PG:

```text
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.SyntaxError) syntax error at or near "1"
[SQL: ALTER TABLE source_revisions ADD CONSTRAINT ck_source_revision_active_slot
 CHECK ((status = 'active' AND active_slot IS 1) OR ...)]
```

Occurs in `20261003_0006_day3_rework_closure.py` — SQLite boolean literal `IS 1` is invalid on PostgreSQL. Fresh PG installs **cannot reach** `20261124_0021` without prior repair of earlier revisions (separate Gate B scope unless bundled into foundation recovery strategy).

## PostgreSQL `20261124_0021` isolated steps (0020-equivalent schema)

After manual creation of `d13_replay_reservations` and `ALTER TABLE ... ADD synthetic_test_only boolean`:

| Step | SQL (from migration source) | SQLSTATE / error |
| --- | --- | --- |
| Backfill | `UPDATE ... SET synthetic_test_only = 1 WHERE json_extract(metadata_json, '$.d13_synthetic_test_only') = true` | **42883** `function json_extract(json, unknown) does not exist` |
| Separate PG-native probe | `metadata_json->>'d13_synthetic_test_only' = 'true'` | **Succeeds** on disposable row (not migration code) |
| Boolean assignment probe | `SET synthetic_test_only = 1` | **42804** `column "synthetic_test_only" is of type boolean but expression is of type integer` |
| Check probe | `CHECK (synthetic_test_only = 1)` after integer assignment | **42804** (same class) |

**Classification:** Dual blocker — SQLite-only `json_extract` **and** integer literal/`CHECK (flag = 1)` incompatible with PostgreSQL `boolean`.

## SQLite `20261124_0021` behavior

**Empty database:** upgrade succeeds; constraint `ck_d13_replay_synthetic_marker` requires `synthetic_test_only = 1` for **all** rows (global synthetic-only table semantics).

**Populated database (synthetic fixtures):**

`json_extract` typing before upgrade (same connection):

| Row id | Marker JSON | `json_extract` value | `typeof` |
| --- | --- | --- | --- |
| bool-true | `true` | `1` | integer |
| int-one | `1` | `1` | integer |
| str-true | `"true"` | `true` | text |
| absent | `{}` | `NULL` | null |
| null | `null` | `NULL` | null |

**Fail-closed populated upgrade:** mixed true + absent rows → Alembic exits `1`, version remains `20261124_0020`, `synthetic_test_only` column **not** present (SQLite transactional DDL rollback observed).

**WAL:** `PRAGMA journal_mode=WAL` before `0021` with single valid row — upgrade **PASS**.

## Environment limitations

- **Driver:** `psycopg2-binary` installed in ephemeral backend venv for diagnostics only (not committed).
- **Docker / CI PG job:** not used this candidate; GitHub Actions PG migrate remains **NOT_RUN** for this SHA until Gate B proposes workflow evidence.
- **Deployed DB state:** unknown — strategy selection requires Founder confirmation per `C01-GATE-B-DECISION.md`.

## Sanitized commands

See `docs/execution/C01-gate-a/run_gate_a_diagnostics.sh` (guarded `ALLOWLIST` paths/ports). Logs:

- `docs/execution/C01-gate-a/pg_fresh_upgrade_head.log`
- `docs/execution/C01-gate-a/sqlite_marker_matrix.log`
- `docs/execution/C01-gate-a/pg_isolated_0021_steps.log`