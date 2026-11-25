# C01 Gate B decision packet (design only — NOT AUTHORIZED)

**Gate B status:** `LOCKED_PENDING_SEPARATE_FOUNDER_STRATEGY_APPROVAL`  
**Gate A outcome:** Root cause for `20261124_0021` reproduced on disposable PostgreSQL; additional PG blocker at `20261003_0006` prevents reaching `0021` via fresh full chain.

## Why a successor alone is insufficient

A new revision `0022`+ cannot run on databases that **never successfully applied `2021`** if fresh PostgreSQL installs cannot pass `0021` during `alembic upgrade head`. Alembic must execute the historical `0021` file (or an authorized compatibility replacement with explicit applied-history policy). Successor DDL does not retroactively repair blocked upgrade paths.

## Feasible alternatives (Founder choice required)

| Option | Summary | Fresh PG install | Already at 0020 | Already at broken partial 0021 | Risk |
| --- | --- | --- | --- | --- | --- |
| **A — Amend `0021` in place** | Portable JSON boolean extraction + `CHECK (synthetic_test_only IS TRUE)` + typed boolean assignment | Repair chain only if `0006`+ also fixed | Requires preflight + backfill semantics | Manual reconciliation / backup | Changes historical revision checksum |
| **B — Split compatibility** | Leave `0021` archived; insert `0021b` with `down_revision=0020` + deprecate `0021` in docs | Needs branch/merge policy for dual paths | Complex reconciliation | High |
| **C — Baseline re-home** | New baseline snapshot for PG-only greenfield (non-prod) | Works greenfield only | Abandons single-chain Alembic history | — | Violates single-history invariant unless Founder approves |

**Recommendation (bounded, fail-closed):** Option **A** as a **controlled historical amendment bundle**: (1) fix known PG portability defects in `0006` (and audit `0006`–`0020` for `IS 1` / SQLite functions), (2) replace `0021` `upgrade()` SQL with dialect-aware JSON truth test and boolean-safe CHECK, (3) **preflight** rejecting rows that are not strictly JSON `true` before DDL, (4) add **successor `0030+`** per C01-16 graph for held work — **only after** Founder approves applied-history rules.

## Exact proposed change surface (not implemented)

| Area | File / symbol | Change |
| --- | --- | --- |
| JSON marker read | `backend/migrations/versions/20261124_0021_d13_replay_synthetic_flag.py` `upgrade()` | Replace `json_extract` + `= true` with portable SQLAlchemy `op.get_bind().dialect.name` branch: PG `(metadata_json->>'d13_synthetic_test_only')::jsonb = 'true'::jsonb` strict **or** `jsonb_typeof(...)='boolean' AND ...='true'`; SQLite strict `json_extract` only on JSON text column type |
| Boolean assignment | same | `SET synthetic_test_only = true` (not `= 1`) |
| CHECK | same | `synthetic_test_only IS TRUE` (PG) / `synthetic_test_only = 1` acceptable SQLite-only if required by batch mode — prefer `IS TRUE` parity |
| Preflight | **new** service `d13_replay_migration_preflight.py` (Gate B) | Abort if any row lacks strict JSON boolean `true`; classify int `1`, string `"true"`, absent as **reject** (no silent promotion) |
| Earlier PG blocker | `20261003_0006_day3_rework_closure.py` | Replace `active_slot IS 1` with `IS TRUE` / `= true` PG-safe |
| Held collision | new ids `20261125_0030..0032` | Per `C01-MIGRATION-INVENTORY.md` |

## Data disposition (requires Founder approval before any write)

| Marker class | Gate A classification | Proposed action |
| --- | --- | --- |
| JSON `true` | Strict eligible | Set `synthetic_test_only=true` |
| JSON `false` / absent / null | Not synthetic | **Abort migration** until explicit quarantine strategy approved |
| JSON integer `1` | **Not authoritative eligible** (SQLite `json_extract` ambiguity) | Abort; manual review |
| JSON string `"true"` | Untrusted | Abort |
| `replayed` without payload integrity | Contradictory | Abort (existing `0020` checks) |

No silent relabel, delete, or quarantine writes in Gate A.

## Test matrix (Gate B execution)

1. Fresh SQLite empty → head green.
2. Fresh PostgreSQL empty → head green (after `0006` fix + `0021` fix).
3. Populated SQLite: strict-true only → `0021` green; mixed → fail with no partial column.
4. Populated PG: same cases via `psycopg2`.
5. Downgrade `0021` → `0020` boundary (destructive limits documented).
6. Alembic `check` + model parity (`C01-14`).
7. CI job: disposable PG service on included runner (proposed, not modified Gate A).

## Founder / infrastructure prerequisites

- Confirm whether any environment already stamped/applied `0021` (version table + column presence).
- Authorize historical revision amendment (Option A) vs successor-only strategy.
- Approve data quarantine rules for non-strict markers.
- Gate B candidate budget (separate approval).

## Remaining C01 tasks (post–Gate B approval)

C01-09..14, C01-17..27 — `NOT_STARTED` (see `C01-GATE-A-SCOPE-MAP.md`).