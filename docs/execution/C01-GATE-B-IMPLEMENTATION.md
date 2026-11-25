# C01 Gate B implementation evidence (candidate 1/3)

**Gate B seed:** `1bcf85c30b24e5f2ce2b4a02dca198f86353861e`  
**Parent Gate A HEAD:** `905cd5810f32cc3e945523edd4560c281ab177bc`  
**Frozen develop:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Deployed production/dev state:** **UNKNOWN** — external rollout remains locked.

## Approved historical edits (post-change SHA-256)

| File | Revision | SHA-256 |
| --- | --- | --- |
| `backend/migrations/versions/20261003_0006_day3_rework_closure.py` | `20261003_0006` | `a6ca3c902156cbf3b9f60dc2b76a9156a405fbfb3cb3130112295e20b5c9a2d2` |
| `backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py` | `20261124_0021` | `fbd1db2a42017c0dc613ea1032db5b090642b68066b315fac65dfb5dab85769f` |
| `backend/migrations/c01_d13_synthetic_preflight.py` | (helper) | `70c51eef5d9497c85042cc482e56608091147276e3b5789dc1395692da45c8a0` |
| `backend/app/models/source.py` | ORM | `ck_source_revision_active_slot` portable INTEGER |
| `backend/app/models/day13_replay.py` | ORM | `synthetic_test_only IS TRUE` |

Revision IDs and `down_revision` links are unchanged.

## Data safety (abort-only)

- `0021`: `assert_0021_preflight()` on raw JSON text (PG `::text`, duplicate-aware `object_pairs_hook`) **before** column DDL; migration aborts on any ineligible row.
- No stamp/skip/delete/quarantine; already-applied untrusted `0021` flags require separate Founder reconciliation (design only).
- Populated mixed markers: disposable proof — upgrade **aborts** at preflight; version remains `20261124_0020`.

## Test matrix (executed)

| Case | SQLite disposable | PG 16 disposable |
| --- | --- | --- |
| Fresh `upgrade head` | **PASS** (`test_sqlite_fresh_upgrade_head`) | **PASS** (`test_postgresql_fresh_upgrade_head`) |
| `0021` strict-only rows | **PASS** | (via fresh head) |
| `0021` mixed/absent marker | **FAIL closed** (preflight) | — |
| `0006` active_slot CHECK probe | **PASS** | (via fresh head) |
| Preflight unit (int/string/dup) | **PASS** | — |

**CI:** `.github/workflows/ci.yml` job `migration-postgres-disposable` (PG 16 service) + existing SQLite migration round-trip.

## Gate A findings closed in code

| ID | Closure |
| --- | --- |
| R3-A01 / F02 | Path `json_type` + raw preflight module |
| R3-A02 / F01 | `active_slot IS NOT NULL AND active_slot = 1` |
| R3-A03 | Tests use owned temp DBs; PG job added |
| R3-A05 | Portable `IS TRUE` synthetic CHECK |

## Remaining blockers

- Sanitized deployed `alembic_version` / partial `0021` evidence still required before real rollout.
- C01-18..25 foundation breadth and B03 items: **PARTIAL** in candidate 1 — not full Gate B acceptance.
- Held PR31/57/61 unchanged; no successor migrations created.