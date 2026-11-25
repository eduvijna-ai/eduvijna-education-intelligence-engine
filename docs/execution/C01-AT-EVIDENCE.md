# C01 AT01–AT10 evidence packet

**Delivery branch:** `closure/c01-acceptance-test-recovery`  
**Prior AT evidence SHA:** `55998081013fb57399e4d1a0f389cfa90d79f300` (CI295 **FAILED** run `45598887196`)  
**Harness correction:** Founder comment `7160951822`; governance seed `fdcf2b6a8bb8b4cec1ef8dbe09574f9516c3d81a`  
**Correction candidate SHA:** `c4e17e6df69e7d235578636f9b8274131f3e5c7a`  
**Local correction run:** Cloud Agent, Python 3.12, backend `.venv`  
**Raw pytest (original):** `docs/execution/C01-AT-PYTEST-RAW.txt`  
**Raw pytest (correction):** `docs/execution/C01-AT-PYTEST-RAW-CORRECTION.txt`  
**JUnit:** `docs/execution/C01-AT-junit.xml` (CI upload: `docs/execution/C01-AT-junit-ci.xml`)

## Summary matrix (local agent)

| Dialect | Collected | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: | ---: |
| Run | Collected | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: | ---: |
| Original local (`5599808` ancestry) | 53 | 49 | 4 | 0 |
| Harness correction local | 54 | 50 | 4 | 0 |
| CI295 exact-head (`5599808`) | — | — | — | **FAILED** (harness/CI; see repair proposal H-01..H-04) |

Skipped tests (infrastructure, not PASS):

- `test_at01_pg_creates_exclusively_owned_empty_database`
- `test_at02_postgres_rejects_false_and_null_synthetic`
- `test_at09_pg_dump_restore_roundtrip`
- `test_postgresql_fresh_empty_upgrade_head` (portability harness)

## Product tree proof

`git diff e7ce396aa088dab2cbdfebadab1ae0d4efaaef67 -- backend/app backend/migrations backend/frontend` → **empty** (no product/migration/model changes).

Allowed paths on this delivery: `backend/tests/**`, `backend/pyproject.toml` (pytest markers), `.eduvijna/pytest-targets.txt`, `.github/workflows/targeted-ci.yml`, `.eduvijna/execution-state.yml`, `docs/execution/C01-AT-*`.

## Revision graph / helpers (frozen baseline)

| Artifact | SHA-256 (file) |
| --- | --- |
| `migrations/c01_revision_graph.py` | recorded at run time via `revision_graph_token()` in AT10 |
| `migrations/c01_d13_synthetic_preflight.py` | unchanged vs Package S `e7ce396` |
| `migrations/c01_constraints.py` | unchanged vs Package S `e7ce396` |

Alembic head at evidence time: `20261124_0021` (single head).

## AT03 digest behavior (SQLite hostile fixture)

- Pre-upgrade row digest captured at `0020`.
- Failed `upgrade 0021` leaves `alembic_version=20261124_0020`, no `synthetic_test_only` column, identical row + schema digests.

## AT08 populated backup

Fixture counts before backup: `organizations=1`, `institutions=1`, `sources=1`, `source_revisions=1`, `d13_replay_reservations=1`.  
`PRAGMA integrity_check=ok`, `foreign_key_check` empty after restore.

## Outstanding / CI-pending

- Disposable PostgreSQL service proofs (AT01 PG create, AT02 PG CHECK, AT09 dump/restore, portability PG fresh head) — **PENDING** GitHub `c01-migration-postgres` job on exact HEAD.
- Full historical `tests/` regression — **NOT_RUN** (budget / Package F locked).
- Compose smoke — **NOT_RUN** (Package F locked).