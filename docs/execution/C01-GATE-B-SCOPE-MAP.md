# C01 Gate B scope map (27 tasks) — candidate 3/3 (final)

**Gate A milestone:** 1 diagnostic PASS (C01-04), 9 PARTIAL/BLOCKED active, 17 NOT_STARTED (historical).  
**Gate B:** candidate **3/3** — **not** technical acceptance; deployed state **UNKNOWN**.

| Task | Gate | Outcome (B cand. 3) | Evidence |
| --- | --- | --- | --- |
| C01-01 | B | **PARTIAL** | Overlay unchanged scope; ledger refs |
| C01-02 | B | **PARTIAL** | Gate B implementation + candidate 3 response |
| C01-03 | B | **PARTIAL** | Historical hashes in implementation doc |
| C01-04 | A→B | **PASS** (setup) | Disposable PG/SQLite CI + strict URL |
| C01-05 | B active | **PARTIAL** | SQLite populated 0018→0021; PG fresh empty proof in CI |
| C01-06 | B active | **PARTIAL** | `test_c01_migration_portability.py` (12 local pass) |
| C01-07 | B active | **PARTIAL** | Preflight + legacy audit + state invariants |
| C01-08 | B active | **PARTIAL** | Decision packet; bounded amendments only |
| C01-09 | B | **PARTIAL** | Historical `0006`/`0021` + ORM CAST parity |
| C01-10 | B | **PARTIAL** | Fresh head SQLite + PG disposable |
| C01-11 | B | **PARTIAL** | Hostile marker / invalid replay state preflight |
| C01-12 | B | **PARTIAL** | `0021` downgrade/reupgrade SQLite; backup **NOT_RUN** |
| C01-13 | B | **PARTIAL** | Abort-at-preflight mixed marker; failure partial |
| C01-14 | B | **PARTIAL** | Model DDL + migration CAST CHECK tests |
| C01-15 | B | **PARTIAL** | Planning only; held hashes preserved |
| C01-16 | B | **NOT_STARTED** | No successor files |
| C01-17 | B active | **NOT_RUN** | Backup/restore — not executed |
| C01-18 | B active | **PARTIAL** | Targeted pytest list includes D3/migration tests |
| C01-19 | B | **NOT_STARTED** | — |
| C01-20 | B | **NOT_STARTED** | — |
| C01-21 | B | **NOT_STARTED** | — |
| C01-22 | B | **NOT_STARTED** | — |
| C01-23 | B | **NOT_STARTED** | — |
| C01-24 | B | **NOT_STARTED** | — |
| C01-25 | B | **NOT_STARTED** | — |
| C01-26 | B | **PARTIAL** | `c01-migration-postgres` fixed DATABASE_URL |
| C01-27 | B | **PARTIAL** | Scope map + candidate 3 response |

**Counts:** 27 tasks; **0** Gate B overall **ACCEPTED**; `gate_b_candidates_consumed: 3`.