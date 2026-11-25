# C01 Gate B implementation evidence (candidate 3/3 final)

**Gate B seed:** `1bcf85c30b24e5f2ce2b4a02dca198f86353861e`  
**Parent Gate A HEAD:** `905cd5810f32cc3e945523edd4560c281ab177bc`  
**Frozen develop:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Deployed production/dev state:** **UNKNOWN** — external rollout remains locked.

## Approved historical edits (post-change SHA-256)

| File | Revision | SHA-256 |
| --- | --- | --- |
| `backend/migrations/versions/20261003_0006_day3_rework_closure.py` | `20261003_0006` | `a6ca3c902156cbf3b9f60dc2b76a9156a405fbfb3cb3130112295e20b5c9a2d2` |
| `backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py` | `20261124_0021` | `b25f01923e75234844d84068628ab03191a23db3062a3304ab072ab5b6d81f56` |
| `backend/migrations/c01_d13_synthetic_preflight.py` | (helper) | (see `git rev-parse HEAD` tree) |
| `backend/app/models/source.py` | ORM | `6b9f5ce80edec7a6a6d585e40da996ca41dcb94b810a12303d7bf32d6a89ac7d` |
| `backend/app/models/day13_replay.py` | ORM | `45a0c3c95f1a612c84380db59ec0ec1bf057b2d1a8edb41ca03c184ddbc0eec3` |

Revision IDs and `down_revision` links are unchanged.

## Data safety (abort-only)

- `0021`: raw JSON preflight + PG table lock before scan; portable `CAST(synthetic_test_only AS INTEGER) = 1` CHECK.
- Legacy `audit_legacy_0021_state()` is read-only; does not trust integer-promoted rows without strict JSON boolean `true`.
- No stamp/skip/delete/quarantine.

## Test matrix (executed locally)

| Case | SQLite disposable | PG 16 disposable (CI opt-in) |
| --- | --- | --- |
| Fresh `upgrade head` | **PASS** | **PASS** (CI job) |
| `0021` strict-only rows | **PASS** | (via fresh) |
| `0021` mixed/absent marker | **FAIL closed** | — |
| Invalid replay state at preflight | **FAIL closed** | — |
| Synthetic CHECK 0/2/-1 | **PASS** | — |
| Preflight unit | **PASS** | — |

**CI:** `targeted-ci.yml` `c01-migration-postgres` + `ci.yml` `migration-postgres-disposable`.

## Remaining blockers

- Sanitized deployed `alembic_version` / partial `0021` still required before real rollout.
- C01-17 backup/restore **NOT_RUN**; C01-19..25 **NOT_STARTED**.
- No Gate B technical acceptance; C02/Day19 locked.

**Gate B candidates:** **3/3 consumed** — await Founder independent review.