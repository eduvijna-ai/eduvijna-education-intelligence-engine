# C01 Gate A diagnostics

**Harness:** `docs/execution/C01-gate-a/c01_gate_a_harness.py`
**Wrapper:** `docs/execution/C01-gate-a/run_gate_a_diagnostics.sh`
**Reference run:** `c01_gatea_3528d62e02f2` → `transcripts/c01_gatea_3528d62e02f2_SUMMARY.json`

## Candidate 3 harness trials

| Trial | Exit | Meaning |
| --- | ---: | --- |
| `sqlite_marker_matrix` | 0 | Preflight + strict SQL matrix; **0 mismatches** |
| `pg_fresh_head` | 100 | **EXPECTED_FAILURE** — `active_slot IS 1` at `0006` |
| `pg_upgrade_0020` | 100 | **EXPECTED_FAILURE** / blocked before `0020` |
| `pg_isolated_0021` | 100 | **EXPECTED_FAILURE** — `json_extract` + boolean=int CHECK |
| `pg_marker_matrix` | 0 | Strict SQL; dup keys need preflight (PG cast collapses) |
| `pg_active_slot_constraints` | 0 | Portable CHECK + UNIQUE probes |
| `sqlite_fresh_head` | 0 | Head `20261124_0021` |
| `sqlite_mixed_0021` | 100 | **EXPECTED_FAILURE** — `ck_d13_replay_synthetic_marker` rollback @ `0020` |
| `sqlite_active_slot_constraints` | 0 | Portable CHECK + UNIQUE probes |

Exit code **100** = diagnostic proved expected failure (not harness broken).

## SQLite strict predicate (corrected — R3-A01)

Use path form (not `json_type(json_extract(...))`):

```sql
json_valid(metadata_json)
AND json_type(metadata_json) = 'object'
AND json_type(metadata_json, '$.d13_synthetic_test_only') = 'true'
```

Reference transcript excerpt (`c01_gatea_3528d62e02f2_sqlite_marker_matrix.log`):

| id | preflight | strict_sql | legacy json_extract |
| --- | --- | --- | --- |
| bool-true | eligible | 1 | 1 |
| int-1 | not | 0 | 1 (legacy conflation) |
| str-true | not | 0 | `'true'` |
| dup-true-false | not | 1 | ambiguous — preflight rejects |

## PostgreSQL errors (unchanged classification)

1. **`json_extract`:** SQLSTATE **42883**
2. **`CHECK (flag = 1)` on boolean:** `operator does not exist: boolean = integer`
3. **Fresh chain:** SyntaxError / invalid `IS 1` on INTEGER at `0006`

## Environment

- PostgreSQL **16.15**, `127.0.0.1:55432`, role `c01_diag`
- Ephemeral `psycopg2-binary` in local venv (not committed)
- **No** production / shared dev connections

## Superseded

Candidate 1 shell harness and candidate 2 marker table claiming inverted strict results — superseded by reference run above.