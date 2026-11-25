# C01 foundation reconciliation (Gate A)

## Authority read (C01-01/02)

| Source | Role |
| --- | --- |
| `AGENTS.md` | Engineering contract; Day19 locked; no `founder_approval` mutation |
| `.eduvijna/execution-state.yml` | C01 `ACTIVE_GATE_A`; C00 provisional merge `1781f036` |
| Issue #66 / #64 | 27-task C01 scope; Gate A = 01–08, 15–16 |
| `docs/execution/D01-FOUNDATION.md`, `D02-CANONICAL-DOMAIN-MODEL.md` | Original Day1/2 obligations |
| `docs/execution/D03-FINAL-COMPATIBILITY-CLOSURE.md` | D3-R11/R12 compatibility |
| `docs/execution/C00-MASTER-TASK-EVIDENCE.csv` | 714 rows; **68** tagged `closure_workstream=C01` |
| `docs/execution/C00-MIGRATION-INVENTORY.md` | Prior audit migration summary |
| `docs/execution/D13-CLOSEOUT-RELEASE-GATES.md` | RB-10 PG `0021` NOT_RUN — **now partially run** in disposable PG |

**Narrow D13-31A exception exercised:** investigation of `20261124_0021` only — no repair, no replay business logic changes.

## 68 provisional C01 rows

Crosswalk: `docs/execution/C01-gate-a/C01-FOUNDATION-RECONCILIATION-OVERLAY.csv` (master CSV **not** bulk-rewritten).

| Metric | Value |
| --- | --- |
| Rows with `closure_workstream=C01` in C00 master | **68** |
| Additional omissions identified (Gate A) | **2** (`C01-OMIT-PG0006`, `C01-OMIT-0021-DATA`) |
| Overlay total rows | **70** |
| Broad technical PASS claimed | **0** |
| C00-R01..05 / MS-001 | **Preserved unresolved** |

Disposition for all 68 provisional rows: **reconciled to original authority text** with `RECONCILED_PROVISIONAL_AWAITING_GATE_B` — historical evidence from C00 audit retained; live migration evidence added only where Gate A ran (PG/SQLite).

## Historical vs current evidence

| Topic | Historical (pre–Gate A) | Current (Gate A candidate 1) |
| --- | --- | --- |
| PG `0021` live failure | Documented / NOT_RUN (D13 RB-10) | **Reproduced** on disposable PG 16.15 |
| SQLite `0021` | Assumed engineering path | Fresh **PASS**; populated mixed **FAIL** |
| Full PG fresh install | Not evidenced | **FAIL at `0006`** before `0021` |
| Held `0022` collision | C00 inventory | Reconfirmed PR57 vs PR61 same revision id |

## Candidate 2 review corrections (C01-A-F01..F05)

- **F01:** `active_slot` confirmed **INTEGER** (`0005`, `source.py`); Gate B design no longer proposes `IS TRUE` on integer.
- **F02:** Strict JSON boolean predicates documented with disposable probe transcripts.
- **F03:** Replaced non-reproducible shell harness with `c01_gate_a_harness.py` + raw logs under `transcripts/`.
- **F04:** Overlay builder adds keyed rows (`D1-DOD-07`, `D3-R11/12`, omissions w/ `parent_task_id`); PR31 held head **`20261109_0018`** (not `0021`).
- **F05:** Scope map outcomes downgraded to **PARTIAL** where appropriate; CI run `45572420611` recorded separately.

See `docs/execution/C01-INDEPENDENT-REVIEW-RESPONSE.md`.

## Explicit non-actions (Gate A)

- No edits to `backend/migrations/**` (including `0021`)
- No app/, frontend, CI workflow, or test suite changes
- No held PR import; no production DB access