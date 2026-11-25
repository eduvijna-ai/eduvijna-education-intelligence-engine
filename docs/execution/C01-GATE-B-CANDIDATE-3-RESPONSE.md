# C01 Gate B candidate 3/3 — R3-B01..B05 response

**Delivery:** branch `closure/c01-foundation-database-recovery`, Draft PR #67.  
**Gate B seed:** `1bcf85c30b24e5f2ce2b4a02dca198f86353861e`  
**Frozen develop:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Deployed history:** **UNKNOWN** — rollout still blocked.

## R3-B01 — CI / disposable PostgreSQL proof

| Fix | Evidence |
| --- | --- |
| `DATABASE_URL` + `EDUVIJNA_C01_DISPOSABLE_*` on PG jobs | `.github/workflows/targeted-ci.yml`, `ci.yml` |
| Empty-schema assert before pytest; **no** bare `alembic upgrade` before tests (avoids double-upgrade / SQLite fallback) | `c01-migration-postgres` job |
| Full `test_c01_migration_portability.py` on draft sync | targeted CI |
| Exact PR head assert (`EDUVIJNA_CANDIDATE_SHA`) | PG job step 1 |
| `postgresql+psycopg` v3 driver | unchanged |

## R3-B02 — ORM / migration portability

| Area | Resolution |
| --- | --- |
| Synthetic CHECK | Shared `CAST(synthetic_test_only AS INTEGER) = 1` in `app/db/c01_portable_checks.py`, migration `0021`, and `day13_replay.py` ORM |
| `0006` | Portable active_slot CHECK retained in `0006` + `source.py` |
| Preflight lock | PG `ACCESS EXCLUSIVE` before preflight scan (0021) |

## R3-B03 — Preflight integrity

| Item | Resolution |
| --- | --- |
| Replay state contract | Preflight rejects invalid state, pending rows with `owner_token`, replayed rows missing payload/version |
| Raw JSON | PG `::text` / SQLite `CAST` only |
| Legacy audit | `audit_legacy_0021_state()` → typed `LegacyAuditReport` (clean / untrusted / absent / wrong_version / unknown) |

## R3-B04 — Test isolation and evidence

| Item | Resolution |
| --- | --- |
| PG URL allowlist | `tests/c01_disposable_pg.py` — loopback hosts, ports 5432/55432/55433, no query params |
| SQLite proofs | Fresh head, mixed-marker abort, strict 0021, synthetic CHECK rejects 0/2/-1, 0018→0021 populated, downgrade/reupgrade, ORM DDL substring |
| PG proof | `test_postgresql_fresh_empty_upgrade_head` (opt-in + CI service) |
| Backup/restore | **NOT_RUN** (C01-17) — still deferred |

**Local:** `pytest tests/test_c01_migration_portability.py` — **12 passed**, **1 skipped** (PG without opt-in).

## R3-B05 — Foundation breadth

C01-19..25 remain **NOT_STARTED**; C01-17 backup **NOT_RUN**; C01-18 **PARTIAL** via targeted pytest list. No held imports, no new historical revisions.

## Historical file SHA-256 (current tree)

| File | SHA-256 |
| --- | --- |
| `20261003_0006_day3_rework_closure.py` | `a6ca3c902156cbf3b9f60dc2b76a9156a405fbfb3cb3130112295e20b5c9a2d2` |
| `20261124_0021_d13_replay_synthetic_flag.py` | `b25f01923e75234844d84068628ab03191a23db3062a3304ab072ab5b6d81f56` |
| `backend/app/models/source.py` | `6b9f5ce80edec7a6a6d585e40da996ca41dcb94b810a12303d7bf32d6a89ac7d` |
| `backend/app/models/day13_replay.py` | `45a0c3c95f1a612c84380db59ec0ec1bf057b2d1a8edb41ca03c184ddbc0eec3` |

Revision IDs and parents unchanged.

**Gate B candidates consumed:** **3/3** — no fourth candidate authorized.