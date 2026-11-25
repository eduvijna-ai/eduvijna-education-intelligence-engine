# C01 Gate A diagnostics

**Harness:** `docs/execution/C01-gate-a/c01_gate_a_harness.py`
**Wrapper:** `docs/execution/C01-gate-a/run_gate_a_diagnostics.sh`
**Raw transcripts:** `docs/execution/C01-gate-a/transcripts/` (per-run id; no shared DB drops except owned `c01_gatea_*` names)

## Candidate 2 harness run (reference)

Summary: `transcripts/c01_gatea_8de74d78f1f5_SUMMARY.json`

| Trial | Exit | Notes |
| --- | ---: | --- |
| `pg_fresh_head` | 1 | SyntaxError `active_slot IS 1` at `0006` |
| `pg_isolated_0021` | 0 | `json_extract` 42883; `boolean = integer` on CHECK |
| `active_slot_check_probe_pg` | 0 | Portable predicate vs broken `IS 1` |
| `sqlite_fresh_head` | 0 | `20261124_0021` |
| `sqlite_marker_probes` | 1 | Mixed markers; rollback @ `0020` |
| `sqlite_active_slot_probe` | 0 | INTEGER `IS 1` works on SQLite |

## PostgreSQL errors (correct classification)

1. **`json_extract`:** SQLSTATE **42883** — undefined function
2. **`CHECK (synthetic_test_only = 1)`:** `operator does not exist: boolean = integer` (not assignment cast)
3. **`CHECK (synthetic_test_only IS TRUE)` on table with default false rows:** constraint violated — shows migration semantics require all rows true after backfill

## SQLite strict vs legacy (`sqlite_marker_probes` transcript)

| Fixture id | Legacy `json_extract` | Strict `json_type(...)='true'` |
| --- | --- | --- |
| json-true | 1 (integer) | 1 |
| json-int1 | 1 | 0 |
| json-str | text `true` | 0 |
| json-absent | NULL | 0 |
| json-malformed | insert may fail / invalid | 0 |

## Legacy logs (candidate 1 — superseded for reproduction)

- `pg_fresh_upgrade_head.log` — still valid raw Alembic output but harness preferred
- `sqlite_marker_matrix.log` — summary only; use transcripts for audit

## Environment

- PostgreSQL **16.15**, `127.0.0.1:55432`, role `c01_diag`
- Driver: ephemeral `psycopg2-binary` in local venv (not committed)
- **No** production / shared dev connections