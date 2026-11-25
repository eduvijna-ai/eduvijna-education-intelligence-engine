# C01 Gate A scope map (27 explicit tasks)

**Frozen baseline:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`
**Governance seed:** `a347a584ecd637b1c72c78a1bdd5ed23b4b2863d`
**Candidate 3 reference harness run:** `c01_gatea_3528d62e02f2`
**PR #67 CI (docs-only, not DB proof):** workflow `#280` run `45574422240` — backend + frontend **SUCCESS**, Compose **SKIPPED**
**Gate B acceptance:** none — diagnostic **PASS** does not imply Gate B **ACCEPTED**

| Task | Gate | Outcome (candidate 3) | Notes |
| --- | --- | --- | --- |
| C01-01 | A active | **PARTIAL** | 70-row overlay + omissions; C00-R01..05 preserved |
| C01-02 | A active | **PARTIAL** | Governance + F01–F05 + R3-A01..A05 responses |
| C01-03 | A active | **PARTIAL** | 21-revision inventory; deployed `alembic_version` **UNKNOWN** |
| C01-04 | A active | **PASS** (disposable setup) | PG 16.15 `@127.0.0.1:55432`; SQLite `/tmp` owned files |
| C01-05 | A active | **PARTIAL/BLOCKED** | PG fresh **EXPECTED_FAILURE** @ `0006`; populated chain blocked; isolated `0021` reproduced |
| C01-06 | A active | **PARTIAL** | SQLite fresh **PASS**; mixed markers **EXPECTED_FAILURE** @ `0020` rollback |
| C01-07 | A active | **PARTIAL** | Corrected strict SQL + fail-closed preflight design; full marker matrix in harness |
| C01-08 | A active | **PARTIAL** | Gate B decision packet updated; no repair authorized |
| C01-09 | B locked | **NOT_STARTED** | — |
| C01-10 | B locked | **NOT_STARTED** | — |
| C01-11 | B locked | **NOT_STARTED** | — |
| C01-12 | B locked | **NOT_STARTED** | — |
| C01-13 | B locked | **NOT_STARTED** | — |
| C01-14 | B locked | **NOT_STARTED** | — |
| C01-15 | A active | **PARTIAL** | Held `0022` collision; PR31 head **`20261109_0018`** |
| C01-16 | A active | **PARTIAL** | Planning IDs `0030..0032` only; no files created |
| C01-17 | B locked | **NOT_STARTED** | — |
| C01-18 | B locked | **NOT_STARTED** | — |
| C01-19 | B locked | **NOT_STARTED** | — |
| C01-20 | B locked | **NOT_STARTED** | — |
| C01-21 | B locked | **NOT_STARTED** | — |
| C01-22 | B locked | **NOT_STARTED** | — |
| C01-23 | B locked | **NOT_STARTED** | — |
| C01-24 | B locked | **NOT_STARTED** | — |
| C01-25 | B locked | **NOT_STARTED** | — |
| C01-26 | B locked | **NOT_STARTED** | — |
| C01-27 | B locked | **NOT_STARTED** | — |

**Counts:** 27 tasks; **10** active Gate A tasks; **0** overall Gate B acceptance; **1** disposable-environment **PASS** (C01-04 only).