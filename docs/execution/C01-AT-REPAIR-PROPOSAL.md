# C01 AT repair proposals (design only — no implementation)

Test-harness correction run only. **No product repair authorized.** Proposals below require separate Founder approval and must be supported by **valid red test evidence**, not harness defects.

## Historical CI295 test/CI defects (corrected in harness correction run — not product)

| ID | Symptom | Classification | Harness fix (this run) |
| --- | --- | --- | --- |
| **H-01** | AT02 PG `engine.begin` + `rollback` closed transaction | Test defect | Independent connections; migrated `d13_replay_reservations` CHECK |
| **H-02** | AT09 insert after 0021 without `synthetic_test_only=true` | Test defect | 0020→0021 populated fixture path + `synthetic_test_only` enforcement |
| **H-03** | AT10 hardcoded `.venv/bin/pytest` | CI/test defect | `sys.executable -m pytest` |
| **H-04** | Backend targeted CI detached checkout after pytest | CI defect | Checkout PR head up front; assert `EDUVIJNA_CANDIDATE_SHA` before tests |

## Product repair candidates (only if future valid red evidence)

| ID | Prerequisite | Notes |
| --- | --- | --- |
| **R-PG-0021** | CI/hostile PG populated 0020→0021 **FAIL** on frozen product | Prior Gate history suggests possible PG dialect preflight issue — **not re-proven** by CI295 failures (those were harness). Require fresh red test on corrected harness before any migration proposal. |

## Infrastructure (BLOCKED ≠ PASS)

| Item | Status |
| --- | --- |
| Local agent without `EDUVIJNA_C01_DISPOSABLE_PG=1` | Mandatory PG cases **SKIP** |
| Missing `pg_dump`/`psql` on agent | AT09 **SKIP**; CI service expected |

**Removed:** unjustified R-AT01 `Settings.database_url` application-guard repair — normal local SQLite default is **not** an established defect per independent review 7160312290.