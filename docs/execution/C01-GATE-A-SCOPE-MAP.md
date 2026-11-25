# C01 Gate A scope map (27 tasks)

**Baseline:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`
**Candidate 2 review base:** `a5a4e7c312ced61e98bd98421d46a08675a27012` (corrected in candidate 2 push)
**PR #67 CI:** run `45572420611` / workflow `#278` — backend + frontend **SUCCESS**, Compose **SKIPPED** (docs-only; not diagnostic proof)
**Self-signoff:** none

| Task | Gate | Outcome (candidate 2) | Evidence |
| --- | --- | --- | --- |
| C01-01 | ACTIVE | **PARTIAL** | Overlay w/ keyed refs; MS-001 / C00-R01..05 preserved |
| C01-02 | ACTIVE | **PARTIAL** | Governance + F01–F05 response doc |
| C01-03 | ACTIVE | **PARTIAL** | Merged inventory + held hashes; deployed env **UNKNOWN** |
| C01-04 | ACTIVE | **PASS** | Harness + transcripts; PG 16.15 disposable |
| C01-05 | ACTIVE | **PARTIAL/BLOCKED** | PG fresh FAIL `0006`; populated full-chain **BLOCKED**; isolated `0021` reproduced |
| C01-06 | ACTIVE | **PARTIAL** | Raw harness transcripts (fresh PASS; mixed FAIL) |
| C01-07 | ACTIVE | **PARTIAL** | Strict predicates probed; preflight design only |
| C01-08 | ACTIVE | **PARTIAL** | Corrected Gate B packet + CHECK inventory |
| C01-09..14 | LOCKED Gate B | NOT_STARTED | — |
| C01-15 | ACTIVE | **PARTIAL** | Held `0022` collision; PR31 head **`0018`** corrected |
| C01-16 | ACTIVE | **PARTIAL** | Planning IDs only; Founder approval for any file creation |
| C01-17..27 | LOCKED Gate B | NOT_STARTED | — |

**Counts:** 27 tasks; 10 active Gate A; **0** broad PASS.