# C01 Gate B scope map (27 tasks) — candidate 1/3

**Gate A milestone:** 1 diagnostic PASS (C01-04), 9 PARTIAL/BLOCKED active, 17 NOT_STARTED (historical).  
**Gate B:** candidate **1/3** — **not** technical acceptance.

| Task | Gate | Outcome (B cand. 1) | Evidence |
| --- | --- | --- | --- |
| C01-01 | B | **PARTIAL** | Overlay unchanged scope; ledger refs |
| C01-02 | B | **PARTIAL** | Gate B implementation doc |
| C01-03 | B | **PARTIAL** | Inventory + new hashes in `C01-GATE-B-IMPLEMENTATION.md` |
| C01-04 | A→B | **PASS** (setup) | Disposable PG/SQLite CI job |
| C01-05 | B active | **PARTIAL** | PG fresh head **PASS** post-fix; populated chain tests partial |
| C01-06 | B active | **PARTIAL** | SQLite strict/mixed proof in `test_c01_migration_portability.py` |
| C01-07 | B active | **PARTIAL** | Preflight module + unit tests |
| C01-08 | B active | **PARTIAL** | Decision packet; amendments implemented bounded |
| C01-09 | B | **PARTIAL** | Historical `0006`/`0021` amended per approval |
| C01-10 | B | **PARTIAL** | Fresh head PG+SQLite tests |
| C01-11 | B | **PARTIAL** | Hostile marker preflight test |
| C01-12 | B | **NOT_RUN** | Backup/restore proof deferred cand. 1 |
| C01-13 | B | **NOT_RUN** | Downgrade boundary proof deferred |
| C01-14 | B | **PARTIAL** | Model/migration parity checks via `alembic check` in CI |
| C01-15 | B | **PARTIAL** | Planning only; held hashes preserved |
| C01-16 | B | **NOT_STARTED** | No successor files |
| C01-17 | B locked | **NOT_STARTED** | — |
| C01-18 | B | **NOT_STARTED** | Foundation sweep cand. 2+ |
| C01-19 | B | **NOT_STARTED** | — |
| C01-20 | B | **NOT_STARTED** | — |
| C01-21 | B | **NOT_STARTED** | — |
| C01-22 | B | **NOT_STARTED** | — |
| C01-23 | B | **NOT_STARTED** | — |
| C01-24 | B | **NOT_STARTED** | — |
| C01-25 | B | **NOT_STARTED** | — |
| C01-26 | B | **PARTIAL** | CI PG disposable job added |
| C01-27 | B | **PARTIAL** | This map + implementation doc |

**Counts:** 27 tasks; **0** Gate B overall **ACCEPTED**; historical migration repair **implemented** within approved file list only.