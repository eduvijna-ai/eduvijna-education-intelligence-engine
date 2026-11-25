# C01 Gate A scope map (27 tasks)

**Baseline:** develop merge `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Candidate branch HEAD at start:** governance seed `a347a584ecd637b1c72c78a1bdd5ed23b4b2863d`  
**Gate:** A diagnostics/design only — Gate B **NOT_AUTHORIZED**  
**Founder approval:** Issue #66 comment 7156388075  
**Self-signoff:** None — outcomes await Founder + exact-HEAD review

| Task | Gate | Outcome (Gate A candidate 1) | Evidence |
| --- | --- | --- | --- |
| C01-01 | **ACTIVE Gate A** | PARTIAL | `C01-FOUNDATION-RECONCILIATION.md`, overlay CSV |
| C01-02 | **ACTIVE Gate A** | PASS | This map, `execution-state.yml` (candidate metadata only) |
| C01-03 | **ACTIVE Gate A** | PASS | `C01-MIGRATION-INVENTORY.md` |
| C01-04 | **ACTIVE Gate A** | PASS | `C01-GATE-A-DIAGNOSTICS.md` (PG 16.15 disposable, SQLite file-backed) |
| C01-05 | **ACTIVE Gate A** | PARTIAL | Live PG fresh chain stops at `0006`; isolated `0021` SQL reproduced |
| C01-06 | **ACTIVE Gate A** | PASS | SQLite fresh head + populated/mixed failure logs |
| C01-07 | **ACTIVE Gate A** | PASS | Marker matrix + fail-closed preflight in `C01-GATE-B-DECISION.md` |
| C01-08 | **ACTIVE Gate A** | PASS | Repair design packet (`C01-GATE-B-DECISION.md`) — design only |
| C01-09 | LOCKED Gate B | NOT_STARTED | — |
| C01-10 | LOCKED Gate B | NOT_STARTED | — |
| C01-11 | LOCKED Gate B | NOT_STARTED | — |
| C01-12 | LOCKED Gate B | NOT_STARTED | — |
| C01-13 | LOCKED Gate B | NOT_STARTED | — |
| C01-14 | LOCKED Gate B | NOT_STARTED | — |
| C01-15 | **ACTIVE Gate A** | PASS | Held `0022` collision verified (PR57/61) |
| C01-16 | **ACTIVE Gate A** | PASS | Proposed successor graph in `C01-MIGRATION-INVENTORY.md` |
| C01-17 | LOCKED Gate B | NOT_STARTED | — |
| C01-18 | LOCKED Gate B | NOT_STARTED | — |
| C01-19 | LOCKED Gate B | NOT_STARTED | — |
| C01-20 | LOCKED Gate B | NOT_STARTED | — |
| C01-21 | LOCKED Gate B | NOT_STARTED | — |
| C01-22 | LOCKED Gate B | NOT_STARTED | — |
| C01-23 | LOCKED Gate B | NOT_STARTED | — |
| C01-24 | LOCKED Gate B | NOT_STARTED | — |
| C01-25 | LOCKED Gate B | NOT_STARTED | — |
| C01-26 | LOCKED Gate B | NOT_STARTED | — |
| C01-27 | LOCKED Gate B | NOT_STARTED | — |

**Row counts:** 27 unique tasks; 10 active Gate A (01–08, 15–16); 17 `LOCKED_GATE_B` / `NOT_STARTED`.

**Preserved locks:** C00-R01..05, MS-001; C02–C15; Day19; held PR31/57/61; no migration edits.