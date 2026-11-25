# C01 Gate B decision packet (design only — NOT AUTHORIZED)

**Gate B status:** `LOCKED_PENDING_SEPARATE_FOUNDER_STRATEGY_APPROVAL`  
**Candidate 2 corrections:** F01 (`active_slot` INTEGER semantics); F02 (type-preserving JSON); scope escalation protocol.

## Deployed state (Founder evidence required)

Request sanitized per environment:

- `alembic_version` / partial failed `0021` (column present without version bump?)
- Backup / restore posture
- Whether SQLite engineering DBs ever applied `0021` (untrusted `synthetic_test_only=1` from integer promotion)

**No production access in Gate A.**

## Fresh-chain reality

| Path | Evidence |
| --- | --- |
| SQLite empty → `20261124_0021` | **PASS** (harness transcript) |
| PostgreSQL empty → head | **FAIL** at `20261003_0006` before `0021` |
| PostgreSQL populated Alembic `0020→0021` | **BLOCKED** — cannot reach `0020` on full chain |
| Isolated PG `0019/0020`-shaped + `0021` SQL steps | **FAIL** (documented transcripts) |

Successor-only `0022+` **cannot** repair fresh PG installs blocked at `0006` or `0021`.

## F01 — `0006` / `SourceRevision` (INTEGER `active_slot`)

**Incorrect candidate-1 proposal:** `IS TRUE` / `= true` on `active_slot` — **rejected** (`active_slot` is nullable `Integer`, `backend/app/models/source.py`).

**Portable invariant (design):**

```sql
(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1)
OR (status <> 'active' AND active_slot IS NULL)
```

Matches `0005` intent (`active_slot = 1` when active). Probe: disposable PG/SQLite (`*_active_slot_check_probe.log`).

**Founder approval required** to touch:

- `20261003_0006_day3_rework_closure.py`
- `backend/app/models/source.py` `ck_source_revision_active_slot`
- Any other migration/model CHECK pairs from `C01-CHECK-CONSTRAINT-INVENTORY.md`

## F02 — `0021` strict JSON boolean (type-preserving)

**Rejected:**

- `(metadata_json->>'key')::jsonb = 'true'::jsonb` (string `"true"` coerces)
- `json_extract(...) = true` on SQLite (integer `1` matches)

**Proposed preflight predicate (abort before DDL):**

- Reject duplicate `"d13_synthetic_test_only"` keys on **raw JSON text** before PostgreSQL `::jsonb` cast (cast collapses duplicates).
- Reject NULL marker, non-object root, and non-boolean-`true` values (no integer `1`, no string `"true"`).

| Dialect | Expression (design) |
| --- | --- |
| PostgreSQL | `jsonb_typeof((metadata_json::jsonb)->'d13_synthetic_test_only') = 'boolean' AND (metadata_json::jsonb)->>'d13_synthetic_test_only' = 'true'` |
| SQLite | `json_valid(metadata_json) AND json_type(metadata_json)='object' AND json_type(metadata_json,'$.d13_synthetic_test_only')='true'` (path `json_type`; **not** `json_type(json_extract(...))`) |

**Probe results (isolated PG):** `m-bool` eligible; `m-int`, `m-str` **not** eligible.

**Post-backfill column / CHECK:**

- Assignment: `synthetic_test_only = true` (typed boolean)
- Table guard: reject any row with `synthetic_test_only IS NOT TRUE` before global `CHECK (synthetic_test_only IS TRUE)` (migration semantics currently force **all** rows true — incompatible with fail-closed preflight unless narrowed)

**Already-applied SQLite `0021` audit:** Rows may have `synthetic_test_only=1` from integer `json_extract` promotion; **do not trust flag without strict re-derive**. Propose successor reconciliation query or refuse runtime activation until Founder data disposition.

**Disposition:** abort-only preflight default; no quarantine/delete without separate approval.

## Gate B option matrix (unchanged structure, corrected technical detail)

| Option | Notes |
| --- | --- |
| **A — Bounded historical amendment** | `0006` + `0021` + model parity; Founder approves exact SHAs/files |
| **B — Split revision graph** | High reconciliation cost |
| **C — Greenfield re-home** | Violates single-chain unless Founder waives |

**Scope escalation protocol:** Additional dialect defects from full CHECK inventory require **additive** Founder approval — not silent bundle growth.

## Tests (Gate B only)

1. Portable `active_slot` probe cases → enforced in migration after approval
2. Strict marker matrix on both dialects
3. Fresh PG/SQLite head green after approved amendments
4. Populated mixed → fail closed without partial DDL
5. CI disposable PG job (proposed; not modified Gate A)

## Held work planning

Proposed unique IDs `0030..0032` remain **planning labels only** — no files created in Gate A/B until collision + portability resolved.

## Remaining C01 tasks

C01-09..14, C01-17..27 — `NOT_STARTED`.