# C01 read-only CHECK constraint portability inventory

**Baseline:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Scope:** Gate A static inspection; dialect-specific SQL in merged migrations vs ORM `CheckConstraint` (no edits).

## `active_slot` INTEGER lifecycle (F01)

| Location | Expression | Column type | PG portable? |
| --- | --- | --- | --- |
| `20261002_0005_source_intelligence.py` (initial) | `active_slot IS NULL OR (active_slot = 1 AND status = 'active')` | `Integer` nullable | **YES** (`= 1`) |
| `20261003_0006_day3_rework_closure.py` (replaces) | `(status = 'active' AND active_slot IS 1) OR (status <> 'active' AND active_slot IS NULL)` | same | **NO** — `IS 1` is invalid on PG integer (SyntaxError at DDL) |
| `backend/app/models/source.py` `SourceRevision` | Same as `0006` (`IS 1`) | `Mapped[int \| None]` | **NO** on PostgreSQL DDL generated from model checks |

**Proposed portable invariant (design only; requires separate Founder approval for `0006` + model parity):**

```sql
(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1)
OR (status <> 'active' AND active_slot IS NULL)
```

**Disposable probe results:** `docs/execution/C01-gate-a/transcripts/*_active_slot_check_probe.log`  
**Note:** `status` is `NOT NULL` in `0005`; `UNKNOWN` (SQL three-valued) not exercised for `status` itself.

## `20261124_0021` synthetic marker

| Location | Issue |
| --- | --- |
| `UPDATE … json_extract(metadata_json, '$.d13_synthetic_test_only') = true` | SQLite-only function |
| `SET synthetic_test_only = 1` / `CHECK (synthetic_test_only = 1)` | SQLite boolean idiom; PG requires `boolean` + `IS TRUE` / `= true` |

## Other merged migrations with dialect-sensitive patterns (audit sample)

| File | Pattern | PG risk |
| --- | --- | --- |
| `20261124_0021` | `json_extract` | HIGH — confirmed |
| `20261003_0006` | `active_slot IS 1` | HIGH — confirmed fresh-chain blocker |
| `20261124_0021` | global `CHECK` forcing all rows `synthetic_test_only = 1` | Semantic — fails populated mixed SQLite trial |
| Held `20261125_0023` (PR61) | `randomblob` in `UPDATE` | SQLite-only (not merged) |

**ORM models with `CheckConstraint`:** `source.py`, `question.py`, `examination.py`, `framework_structure.py`, `knowledge_intelligence.py`, `tenancy.py` — full diff vs Alembic not completed in Gate A; **additional defects likely** (scope escalation requires Founder approval before Gate B bundle).

**Gate B:** No automatic expansion beyond inventoried blockers without Founder authorization of exact revision file list.