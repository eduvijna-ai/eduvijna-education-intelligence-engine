# C01 Package S implementation evidence

**Governance seed:** `ef85697ddefcd076fc2862ee77a86c7a8844919f`  
**Authorized baseline:** `ec17e9ba5c5660235a857940d8c1c2d136e1363a` (held Gate B HEAD)  
**Develop baseline:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Branch:** `closure/c01-package-s-database-safety` → `develop` (Draft PR69)

## Historical revision files (pre/post)

| File | Revision | SHA-256 (current tree) | Changed in Package S? |
| --- | --- | --- | --- |
| `backend/migrations/versions/20261003_0006_day3_rework_closure.py` | `20261003_0006` | `a6ca3c902156cbf3b9f60dc2b76a9156a405fbfb3cb3130112295e20b5c9a2d2` | **No** |
| `backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py` | `20261124_0021` | `b25f01923e75234844d84068628ab03191a23db3062a3304ab072ab5b6d81f56` | **No** (imports updated helper at apply time) |

## Helper / model hashes (Package S)

| Path | SHA-256 |
| --- | --- |
| `backend/app/db/c01_portable_checks.py` | `d25b54091736470c91391f51f031ef1d474c4136ea8f6b43ddd5dc2dffe365f0` |
| `backend/app/models/day13_replay.py` | `41d8f7f21ddccfab8fef70e2a14bf3957c813d89d4c012adb9f65a5695ed9dd9` |
| `backend/migrations/c01_d13_synthetic_preflight.py` | `78e6c4ae8d06da412bd727d758394a1de62bdb48b46f8c500f8a82d80dc4be0a` |
| `backend/migrations/c01_revision_graph.py` | (new — 21-node ordered graph) |

Revision IDs and `down_revision` links: **unchanged** (21 revisions ending `20261124_0021`).

## Behavioral amendments (authorized)

1. **Synthetic CHECK:** `CAST(synthetic_test_only AS INTEGER) = 1` replaced with dialect-exact `synthetic_test_only = 1` (SQLite) and `synthetic_test_only IS TRUE` (PostgreSQL) via `d13_synthetic_check_sql()` and `D13_SYNTHETIC_MARKER_CHECK`.
2. **0021 preflight:** Replay rows in `reserved` / `in_progress` must carry non-null `owner_token` (aligned with `durable_replay_envelope._row_integrity`).
3. **Legacy audit:** Graph-indexed revision comparison, column nullability/type/CHECK probes, expanded `LegacyAuditStatus` values (fail-closed).

## Command log (sanitized)

```text
cd backend && .venv/bin/ruff check migrations/c01_*.py app/db/c01_portable_checks.py app/models/day13_replay.py tests/test_c01_migration_portability.py
# All checks passed!

cd backend && .venv/bin/mypy migrations/c01_d13_synthetic_preflight.py migrations/c01_constraints.py migrations/c01_revision_graph.py app/db/c01_portable_checks.py
# Success: no issues found in 4 source files

cd backend && .venv/bin/pytest tests/test_c01_migration_portability.py -v --tb=no
# 17 passed, 1 skipped (postgresql_fresh_empty_upgrade_head — no local PG), 1 warning
```

Full verbose listing: `docs/execution/C01-PACKAGE-S-PYTEST-RAW.txt`

## SQLite cases executed

| Case | Result |
| --- | --- |
| Fresh `upgrade head` | PASS |
| Mixed marker preflight abort @ 0020 | PASS (fail closed) |
| Strict marker 0021 success | PASS |
| Synthetic CHECK rejects 0/2/-1/1.5 | PASS |
| CAST-weak probe (`1junk`) | PASS (IntegrityError) |
| Populated 0018→0021 | PASS |
| Downgrade/re-upgrade 0021 | PASS |
| `in_progress` + owner preflight | PASS |
| Missing owner on pending preflight | PASS (abort) |
| SQLite backup/restore row hash | PASS |
| Legacy audit clean @ 0021 | PASS |
| Legacy audit column absent @ 0020 | PASS |

## PostgreSQL cases

| Case | Local agent | CI expectation |
| --- | --- | --- |
| Fresh empty `upgrade head` | **SKIPPED** (no PG) | `c01-migration-postgres` job |
| pg_dump/restore | **NOT_RUN** | Requires disposable PG |
| Hostile populated matrix | **NOT_RUN** | Deferred to CI / Founder environment |

## CI separation

- Historical Gate B green run **CI 291 / 45591996727** remains audit evidence only — **not** Package S acceptance.
- Package S acceptance requires **exact-head** review on this branch after push.

## External / unresolved

- Deployed dev/prod `alembic_version` and partial `0021` states: **UNKNOWN** — request sanitized evidence only; no live DB access performed.
- Compose verification: **NOT_RUN** (Package F).