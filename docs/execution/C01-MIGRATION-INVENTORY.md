# C01 migration inventory (merged + held)

**Merged develop (21 files):** see `C01-gate-a/migration_sha256.txt`
**Held file hashes:** `C01-gate-a/held_migration_sha256.txt`

## Deployed application history

**UNKNOWN** — Founder sanitized evidence required (`alembic_version`, partial `0021`, backup posture).

## Held branch heads (read-only)

| PR | HEAD | Alembic files at head (max rev) | Relation to `0021` |
| --- | --- | --- | --- |
| #31 Day11 | `d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2` | ends **`20261109_0018`** | **Predates** merged `0019–0021` (Day11 forked before D13 envelope) |
| #57 Day15 | `b69f97bf9ee1cb08e16121f301dc20e5e5645f6f` | through **`20261124_0022`** (learner DDL) | Declares parent `0021` |
| #61 Day17 | `87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1` | **`0022`** (auth) + `20261125_0023` + `0024` | Same **`20261124_0022` id** as #57 — collision |

**No import** of held migrations on C01 branch.

## Duplicate `20261124_0022` (C01-15)

| File | SHA-256 | Parent |
| --- | --- | --- |
| `20261124_0022_day15_learner_intelligence.py` (PR57) | `5612f212…636` | `20261124_0021` |
| `20261124_0022_day17_auth_jobs.py` (PR61) | `e2af81b8…791` | `20261124_0021` |

## Proposed planning graph (C01-16 — IDs only)

After Founder-approved repair of merged head (`0021` + PG chain):

`0021*` → `20261125_0030` (C12 identity) → `0031` (C10 learner) → `0032` (C13 worker) — **not created in Gate A**.